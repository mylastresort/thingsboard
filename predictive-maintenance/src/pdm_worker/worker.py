from pathlib import Path
from typing import Any

from confluent_kafka import DeserializingConsumer, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import StringDeserializer
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

from src.logger import logger
from src.model import job as job_module
from src.model.job import PredictionJobManager
from src.pdm_worker.activation import activate_forecast
from src.pdm_worker.config import WorkerConfig, load_config
from src.pdm_worker.events import PdmEventPublisher


class PdmKafkaWorker:
    def __init__(self, config: WorkerConfig) -> None:
        self._config = config
        self._publisher = PdmEventPublisher(
            bootstrap_servers=config.kafka_bootstrap_servers,
            schema_registry_url=config.schema_registry_url,
            redis_url=config.redis_url,
            event_topic=config.event_topic,
            schema_dir=config.schema_dir,
        )
        self._jobs = PredictionJobManager()
        self._consumer = self._build_consumer(config)
        self._install_event_hooks()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )
    def run(self) -> None:
        self._consumer.subscribe([self._config.command_topic])
        logger.info(
            "PDM Kafka worker subscribed to "
            f"{self._config.command_topic} on {self._config.kafka_bootstrap_servers} "
            f"for modelType={self._config.worker_model_type} "
            f"groupId={self._config.consumer_group}"
        )
        try:
            while True:
                msg = self._consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    raise KafkaException(msg.error())
                command = msg.value()
                try:
                    self._handle_command(command)
                    self._consumer.commit(msg)
                except Exception as exc:
                    logger.exception(f"Failed to handle PDM command {command}: {exc}")
                    forecast_id = str((command or {}).get("forecastId", "unknown"))
                    model_id = f"{forecast_id}/system"
                    self._publisher.log(model_id, "error", f"Command failed: {exc}")
                    self._publisher.flush()
        finally:
            self._consumer.close()
            self._publisher.flush()

    def _build_consumer(self, config: WorkerConfig) -> DeserializingConsumer:
        command_schema = self._read_schema(config.schema_dir, "pdm-commands-value.avsc")
        registry_client = SchemaRegistryClient({"url": config.schema_registry_url})
        return DeserializingConsumer(
            {
                "bootstrap.servers": config.kafka_bootstrap_servers,
                "group.id": config.consumer_group,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
                "key.deserializer": StringDeserializer("utf_8"),
                "value.deserializer": AvroDeserializer(registry_client, command_schema),
            }
        )

    def _handle_command(self, command: dict[str, Any]) -> None:
        command_type = str(command["commandType"]).upper()
        forecast_id = str(command["forecastId"])
        model_type = str(command.get("modelType") or "BOTH").upper()
        device_id = command.get("deviceId")

        if not self._handles_model_type(model_type):
            logger.info(
                f"Skipping PDM command commandType={command_type} forecastId={forecast_id} "
                f"modelType={model_type}; worker handles {self._config.worker_model_type}"
            )
            return

        logger.info(
            f"Handling PDM command commandType={command_type} forecastId={forecast_id} "
            f"modelType={model_type} workerModelType={self._config.worker_model_type}"
        )

        if command_type == "TRAIN":
            activate_forecast(
                forecast_id,
                device_id=device_id,
                model_type=self._config.worker_model_type,
                job_manager=self._jobs,
                progress_callback=self._publisher.progress,
            )
            return

        if command_type == "INFER":
            target_model_id = self._target_model_id(forecast_id)
            handled = self._jobs.start(
                target_model_id,
                self._source_model_type(target_model_id),
                device_id=device_id,
            )
            level = "info" if handled else "warning"
            self._publisher.log(target_model_id, level, f"{command_type} handled={handled}")
            return

        target_model_id = self._target_model_id(forecast_id)
        if command_type == "STOP":
            handled = self._jobs.stop(target_model_id)
        elif command_type == "PAUSE":
            handled = self._jobs.pause(target_model_id)
        elif command_type == "UNPAUSE":
            handled = self._jobs.unpause(target_model_id)
        else:
            raise ValueError(f"Unsupported commandType={command_type}")

        level = "info" if handled else "warning"
        self._publisher.log(target_model_id, level, f"{command_type} handled={handled}")

    def _install_event_hooks(self) -> None:
        original_add_model_log = job_module.add_model_log

        def add_model_log(model_id: str, level: str, message: Any) -> None:
            original_add_model_log(model_id, level, message)
            self._publisher.log(model_id, level, message)
            if level.lower() == "prediction" and isinstance(message, dict):
                self._publisher.prediction(
                    model_id,
                    iteration=message.get("iteration"),
                    model_type=self._source_model_type(model_id),
                    sensor=message.get("sensor"),
                    result=message.get("result", message),
                )

        job_module.add_model_log = add_model_log

    def _handles_model_type(self, command_model_type: str) -> bool:
        return command_model_type == "BOTH" or command_model_type == self._config.worker_model_type

    def _target_model_id(self, forecast_id: str) -> str:
        if self._config.worker_model_type == "ANOMALY":
            return f"{forecast_id}/anomaly_predictor"
        if self._config.worker_model_type == "FORECAST":
            return f"{forecast_id}/forecast_model"
        raise ValueError(f"Unsupported PDM_WORKER_MODEL_TYPE={self._config.worker_model_type}")

    def _source_model_type(self, model_id: str) -> str:
        return "ForecastModel" if "forecast" in model_id.lower() else "AnomalyPredictor"

    def _read_schema(self, schema_dir: Path, filename: str) -> str:
        path = schema_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Avro schema {path} not found. Set PDM_AVRO_SCHEMA_DIR to the directory "
                "containing the PDM Kafka .avsc files."
            )
        return path.read_text(encoding="utf-8")


def main() -> None:
    PdmKafkaWorker(load_config()).run()


if __name__ == "__main__":
    main()
