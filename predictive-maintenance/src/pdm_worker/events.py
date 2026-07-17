import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis
from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import StringSerializer
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

from src.logger import logger
from src.model.job import MAX_LOG_ENTRIES, to_native


class PdmEventPublisher:
    def __init__(
        self,
        *,
        bootstrap_servers: str,
        schema_registry_url: str,
        redis_url: str,
        event_topic: str,
        schema_dir: Path,
    ) -> None:
        event_schema = (schema_dir / "pdm-events-value.avsc").read_text(encoding="utf-8")
        registry_client = SchemaRegistryClient({"url": schema_registry_url})
        self._topic = event_topic
        self._redis = redis.Redis.from_url(
            redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=5,
            retry_on_timeout=True,
        )
        self._producer = SerializingProducer(
            {
                "bootstrap.servers": bootstrap_servers,
                "key.serializer": StringSerializer("utf_8"),
                "value.serializer": AvroSerializer(registry_client, event_schema),
                "message.timeout.ms": 30000,
            }
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )
    def log(self, model_id: str, level: str, message: Any) -> None:
        text = message if isinstance(message, str) else json.dumps(message, default=to_native)
        source = self._source(model_id)
        model_type = "forecast" if "forecast" in model_id.lower() else "anomaly"
        timestamp = self._now_millis()

        redis_entry = {
            "timestamp": datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat(),
            "level": self._redis_level(level),
            "type": model_type,
            "message": message if isinstance(message, dict) else text,
            "source": source,
        }
        key = f"logs:{model_id}"
        self._redis.rpush(key, json.dumps(redis_entry, default=to_native))
        self._redis.ltrim(key, -MAX_LOG_ENTRIES, -1)
        self._redis.expire(key, 24 * 60 * 60)

        self.publish(
            {
                "eventType": "LOG",
                "forecastId": self._forecast_id(model_id),
                "modelId": model_id,
                "iteration": None,
                "timestamp": timestamp,
                "progress": None,
                "prediction": None,
                "alarm": None,
                "log": {
                    "level": self._redis_level(level),
                    "source": source,
                    "message": text,
                },
            }
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )
    def progress(self, model_id: str, progress: dict[str, Any] | None) -> None:
        if not progress:
            return
        percent = int(progress.get("progress", progress.get("percent", 0)))
        step = str(progress.get("step", ""))
        self._write_job_progress(model_id, step, percent)
        self.publish(
            {
                "eventType": "PROGRESS",
                "forecastId": self._forecast_id(model_id),
                "modelId": model_id,
                "iteration": None,
                "timestamp": self._now_millis(),
                "progress": {
                    "step": step,
                    "message": str(progress.get("message", "")),
                    "percent": percent,
                },
                "prediction": None,
                "alarm": None,
                "log": None,
            }
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )
    def prediction(
        self,
        model_id: str,
        *,
        iteration: int | None,
        model_type: str,
        sensor: str | None,
        result: Any,
    ) -> None:
        timestamp = self._now_millis()
        result_json = json.dumps(result, default=to_native)
        self._write_job_running(model_id, iteration)
        self.publish(
            {
                "eventType": "PREDICTION",
                "forecastId": self._forecast_id(model_id),
                "modelId": model_id,
                "iteration": iteration,
                "timestamp": timestamp,
                "progress": None,
                "prediction": {
                    "modelType": model_type,
                    "sensor": sensor,
                    "resultJson": result_json,
                },
                "alarm": None,
                "log": None,
            }
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )
    def publish(self, event: dict[str, Any]) -> None:
        forecast_id = str(event["forecastId"])
        self._producer.produce(
            topic=self._topic,
            key=forecast_id,
            value=event,
            on_delivery=self._delivery_report,
        )
        self._producer.poll(0)

    def flush(self) -> None:
        self._producer.flush()

    def _delivery_report(self, err, msg) -> None:
        if err is not None:
            logger.error(f"Failed to publish PDM event: {err}")

    def _forecast_id(self, model_id: str) -> str:
        return model_id.split("/", 1)[0]

    def _source(self, model_id: str) -> str:
        if "forecast" in model_id.lower():
            return "ForecastModel"
        if "anomaly" in model_id.lower():
            return "AnomalyModel"
        return "System"

    def _redis_level(self, level: str) -> str:
        normalized = level.lower()
        if normalized == "warn":
            return "warning"
        if normalized == "prediction":
            return "prediction"
        return normalized if normalized in {"debug", "info", "warning", "error", "critical"} else "info"

    def _now_millis(self) -> int:
        return int(datetime.now(tz=timezone.utc).timestamp() * 1000)

    def _write_job_progress(self, model_id: str, step: str, percent: int) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        self._redis.hset(
            f"job:{model_id}",
            mapping={
                "status": "RUNNING" if percent >= 100 else "TRAINING",
                "paused": "0",
                "iterations": self._redis.hget(f"job:{model_id}", "iterations") or "0",
                "model_type": self._source_model_type(model_id),
                "start_time": self._redis.hget(f"job:{model_id}", "start_time") or now,
                "last_run": now,
                "training_progress": str(percent),
                "training_step": step,
            },
        )

    def _write_job_running(self, model_id: str, iteration: int | None) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        current_iteration = self._redis.hget(f"job:{model_id}", "iterations") or "0"
        if iteration is not None:
            current_iteration = str(iteration)
        self._redis.hset(
            f"job:{model_id}",
            mapping={
                "status": "RUNNING",
                "paused": "0",
                "iterations": current_iteration,
                "model_type": self._source_model_type(model_id),
                "start_time": self._redis.hget(f"job:{model_id}", "start_time") or now,
                "last_run": now,
            },
        )

    def _source_model_type(self, model_id: str) -> str:
        return "ForecastModel" if "forecast" in model_id.lower() else "AnomalyPredictor"
