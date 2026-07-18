"""Feature engineering worker for PdM pipeline.

Consumes raw telemetry from Kafka or ThingsBoard API, computes rolling stats,
error counts, and component ages incrementally using a sliding buffer, then
publishes pre-computed feature vectors to the pdm-features topic and caches
them in Redis for fast access by inference workers.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import redis
import yaml

from src.logger import logger

_SCHEMA_DIR = Path("/app/tb-quarkus/gateway/src/main/avro")
_REGISTRY_PATH = Path(__file__).parent.parent / "schemas" / "feature_registry.yaml"


def load_registry(path: Path | None = None) -> dict:
    p = path or _REGISTRY_PATH
    with open(p) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Sliding buffer: O(1) incremental rolling stats per device
# ---------------------------------------------------------------------------

class SlidingBuffer:
    """Maintains a fixed-size deque of raw telemetry samples per device.

    On each new sample, appends and drops the oldest entry, then recomputes
    mean/std for the window in O(window_size) using numpy (not O(N) on the
    full history like pandas .rolling()).
    """

    def __init__(self, max_samples: int) -> None:
        self._max = max_samples
        self._buffers: dict[str, dict[str, list[float]]] = {}

    def update(
        self, device_id: str, values: dict[str, float]
    ) -> dict[str, dict[str, float]]:
        if device_id not in self._buffers:
            self._buffers[device_id] = {k: [] for k in values}

        buf = self._buffers[device_id]
        for k, v in values.items():
            if k not in buf:
                buf[k] = []
            buf[k].append(v)
            if len(buf[k]) > self._max:
                buf[k] = buf[k][-self._max:]

        stats: dict[str, dict[str, float]] = {}
        for k, arr in buf.items():
            arr_np = np.array(arr, dtype=np.float64)
            stats[k] = {
                "mean": float(np.mean(arr_np)),
                "std": float(np.std(arr_np, ddof=1)) if len(arr_np) > 1 else 0.0,
            }
        return stats

    def get_buffer(self, device_id: str) -> dict[str, list[float]]:
        return self._buffers.get(device_id, {})


# ---------------------------------------------------------------------------
# Feature computation engine
# ---------------------------------------------------------------------------

class FeatureEngine:
    """Computes all PdM features from raw telemetry, errors, and maintenance data.

    Two modes:
    - batch: process full historical DataFrames (for training)
    - incremental: process one sample at a time using SlidingBuffer (for inference)
    """

    def __init__(self, registry: dict) -> None:
        self._reg = registry
        self._meta = registry["metadata"]
        self._tele_keys = self._meta["telemetry_keys"]
        self._error_keys = self._meta["error_keys"]
        self._comp_keys = self._meta["component_keys"]
        self._feature_cols = registry["feature_columns"]

        # 3h window = 3h / 3h_resample = 1 period
        self._buf_3h = SlidingBuffer(max_samples=1)
        # 24h window = 24h / 3h_resample = 8 periods
        self._buf_24h = SlidingBuffer(max_samples=8)
        # error window: 8 periods of 3h = 24h
        self._buf_errors = SlidingBuffer(max_samples=8)
        # component age: track last replacement datetime per device/component
        self._last_replacement: dict[str, dict[str, datetime]] = {}
        self._machine_age: dict[str, int] = {}

    @property
    def feature_columns(self) -> list[str]:
        return list(self._feature_cols)

    # -- incremental mode (streaming) ----------------------------------------

    def update_telemetry(
        self, device_id: str, ts: datetime, values: dict[str, float]
    ) -> dict[str, float] | None:
        """Update sliding buffers with a new telemetry sample. Returns feature
        vector once enough data is accumulated (after 8 periods = 24h warmup)."""
        stats_3h = self._buf_3h.update(device_id, values)
        stats_24h = self._buf_24h.update(device_id, values)

        buf_24h = self._buf_24h.get_buffer(device_id)
        # need at least 8 samples for 24h stats
        has_24h = all(len(v) >= 8 for v in buf_24h.values()) if buf_24h else False
        if not has_24h:
            return None

        features: dict[str, float] = {}
        for key in self._tele_keys:
            features[f"{key}mean_3h"] = stats_3h.get(key, {}).get("mean", 0.0)
            features[f"{key}sd_3h"] = stats_3h.get(key, {}).get("std", 0.0)
            features[f"{key}mean_24h"] = stats_24h.get(key, {}).get("mean", 0.0)
            features[f"{key}sd_24h"] = stats_24h.get(key, {}).get("std", 0.0)

        # static features
        features["age"] = self._machine_age.get(device_id, 10)

        # component ages
        now = datetime.now(tz=timezone.utc)
        for comp in self._comp_keys:
            last = self._last_replacement.get(device_id, {}).get(comp)
            if last:
                features[comp] = (now - last).total_seconds() / 86400.0
            else:
                features[comp] = 365.0

        return features

    def update_errors(self, device_id: str, error_id: str) -> None:
        error_vals = {ek: 1.0 if ek == error_id else 0.0 for ek in self._error_keys}
        self._buf_errors.update(device_id, error_vals)

    def get_error_counts(self, device_id: str) -> dict[str, float]:
        buf = self._buf_errors.get_buffer(device_id)
        counts: dict[str, float] = {}
        for ek in self._error_keys:
            arr = buf.get(ek, [])
            counts[f"{ek}count"] = float(sum(arr))
        return counts

    def update_replacement(self, device_id: str, component: str, ts: datetime) -> None:
        if device_id not in self._last_replacement:
            self._last_replacement[device_id] = {}
        self._last_replacement[device_id][component] = ts

    def set_machine_age(self, device_id: str, age: int) -> None:
        self._machine_age[device_id] = age

    # -- batch mode (training) -----------------------------------------------

    def compute_batch_features(
        self,
        telemetry_df: pd.DataFrame,
        errors_df: pd.DataFrame | None,
        maintenance_df: pd.DataFrame | None,
        machines_df: pd.DataFrame | None,
    ) -> pd.DataFrame:
        """Compute full feature matrix from historical data (batch mode for training)."""
        features = self._batch_telemetry_features(telemetry_df)
        features["datetime"] = pd.to_datetime(features["datetime"])

        if errors_df is not None and not errors_df.empty:
            error_feats = self._batch_error_features(telemetry_df, errors_df)
            error_feats["datetime"] = pd.to_datetime(error_feats["datetime"])
            features = features.merge(error_feats, on=["datetime", "machineID"], how="left")
        else:
            for ek in self._error_keys:
                features[f"{ek}count"] = 0.0

        if maintenance_df is not None and not maintenance_df.empty:
            comp_feats = self._batch_component_features(telemetry_df, maintenance_df)
            comp_feats["datetime"] = pd.to_datetime(comp_feats["datetime"])
            features = features.merge(comp_feats, on=["datetime", "machineID"], how="left")
        else:
            for ck in self._comp_keys:
                features[ck] = 365.0

        if machines_df is not None and not machines_df.empty:
            age_val = int(machines_df["age"].iloc[0])
            features["age"] = age_val
            self._machine_age[features["machineID"].iloc[0]] = age_val
        else:
            features["age"] = 10

        for col in self._feature_cols:
            if col not in features.columns:
                features[col] = 0.0

        return features[self._feature_cols]

    def _batch_telemetry_features(self, telemetry: pd.DataFrame) -> pd.DataFrame:
        telemetry = telemetry.copy()
        telemetry["datetime"] = pd.to_datetime(telemetry["datetime"])

        mean_parts: list[pd.DataFrame] = []
        std_parts: list[pd.DataFrame] = []

        for key in self._tele_keys:
            pivot = pd.pivot_table(telemetry, index="datetime", columns="machineID", values=key)
            resampled = pivot.resample("3h", closed="left", label="right")

            m3 = resampled.mean()
            m3.columns = [f"{key}mean_3h"]
            mean_parts.append(m3)

            s3 = resampled.std()
            s3.columns = [f"{key}sd_3h"]
            std_parts.append(s3)

            first_24 = resampled.first()
            m24 = first_24.rolling(window=24, center=False).mean()
            m24.columns = [f"{key}mean_24h"]
            mean_parts.append(m24)

            s24 = first_24.rolling(window=24, center=False).std()
            s24.columns = [f"{key}sd_24h"]
            std_parts.append(s24)

        all_feats = pd.concat(mean_parts + std_parts, axis=1)
        all_feats.index.name = "datetime"
        all_feats = all_feats.dropna(subset=[f"{self._tele_keys[0]}mean_24h"])

        # Replicate with each machineID (single-machine dataset or pivot)
        machine_ids = telemetry["machineID"].unique()
        rows = []
        for mid in machine_ids:
            for dt in all_feats.index:
                row = {"datetime": dt, "machineID": mid}
                row.update(all_feats.loc[dt].to_dict())
                rows.append(row)

        features = pd.DataFrame(rows)
        return features

    def _batch_error_features(
        self, telemetry: pd.DataFrame, errors: pd.DataFrame
    ) -> pd.DataFrame:
        telemetry = telemetry.copy()
        telemetry["datetime"] = pd.to_datetime(telemetry["datetime"])

        error_count = pd.get_dummies(
            errors.set_index("datetime"), columns=["errorID"]
        ).reset_index()
        error_count = error_count.astype(int, errors="ignore")

        new_cols = []
        for c in error_count.columns:
            if c.startswith("errorID_"):
                new_cols.append(c.split("errorID_", 1)[1])
            else:
                new_cols.append(c)
        error_count.columns = new_cols

        for ek in self._error_keys:
            if ek not in error_count.columns:
                error_count[ek] = 0

        error_count["datetime"] = pd.to_datetime(error_count["datetime"])
        error_count = (
            telemetry[["datetime", "machineID"]]
            .merge(error_count, on=["machineID", "datetime"], how="left")
            .fillna(0.0)
        )

        # Resample to 3h and compute rolling sum per machine
        error_count = error_count.set_index("datetime")
        machine_ids = error_count["machineID"].unique()

        result_rows: list[dict] = []
        for mid in machine_ids:
            mid_data = error_count[error_count["machineID"] == mid].drop(columns=["machineID"])
            resampled = mid_data.resample("3h", closed="left", label="right").first().fillna(0)
            rolling = resampled.rolling(window=24, center=False).sum()
            for dt in rolling.index:
                row: dict = {"datetime": dt, "machineID": int(mid)}
                for ek in self._error_keys:
                    row[f"{ek}count"] = float(rolling.loc[dt, ek]) if ek in rolling.columns else 0.0
                result_rows.append(row)

        return pd.DataFrame(result_rows)

    def _batch_component_features(
        self, telemetry: pd.DataFrame, maint: pd.DataFrame
    ) -> pd.DataFrame:
        telemetry["datetime"] = pd.to_datetime(telemetry["datetime"])
        maint["datetime"] = pd.to_datetime(maint["datetime"])

        comp_rep = pd.get_dummies(maint.set_index("datetime")).reset_index()
        comp_rep.columns = ["datetime", "machineID"] + self._comp_keys

        comp_rep = (
            telemetry[["datetime", "machineID"]]
            .merge(comp_rep, on=["datetime", "machineID"], how="outer")
            .fillna(0)
            .sort_values(by=["machineID", "datetime"])
        )

        for comp in self._comp_keys:
            comp_rep.loc[comp_rep[comp] < 1, comp] = 0
            comp_rep.loc[comp_rep[comp] != 0, comp] = comp_rep.loc[
                comp_rep[comp] != 0, "datetime"
            ]
            comp_rep[comp] = comp_rep[comp].replace(0, pd.NA).ffill()

        comp_rep = comp_rep.loc[comp_rep["datetime"] > pd.to_datetime("2015-01-01")]

        for comp in self._comp_keys:
            comp_rep[comp] = (
                comp_rep["datetime"] - pd.to_datetime(comp_rep[comp])
            ) / np.timedelta64(1, "D")

        return comp_rep[["datetime", "machineID"] + self._comp_keys]


# ---------------------------------------------------------------------------
# Redis feature cache
# ---------------------------------------------------------------------------

class FeatureCache:
    """Redis-backed cache for pre-computed feature vectors.

    Key pattern: pdm:features:{device_id}
    Stores the latest feature JSON with configurable TTL.
    """

    def __init__(self, redis_url: str, prefix: str = "pdm:features", ttl: int = 300) -> None:
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._prefix = prefix
        self._ttl = ttl

    def put(self, device_id: str, features: dict[str, float], ts: datetime | None = None) -> None:
        key = f"{self._prefix}:{device_id}"
        payload = {
            "features": features,
            "timestamp": (ts or datetime.now(tz=timezone.utc)).isoformat(),
        }
        self._redis.set(key, json.dumps(payload, default=str), ex=self._ttl)

    def get(self, device_id: str) -> dict[str, float] | None:
        key = f"{self._prefix}:{device_id}"
        raw = self._redis.get(key)
        if raw is None:
            return None
        return json.loads(raw).get("features")

    def get_all(self, device_id: str) -> dict | None:
        key = f"{self._prefix}:{device_id}"
        raw = self._redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)


# ---------------------------------------------------------------------------
# Kafka integration
# ---------------------------------------------------------------------------

class FeatureWorker:
    """Standalone Kafka worker that computes features and publishes them.

    Modes:
    - STREAMING: consumes pdm-raw-telemetry, computes incrementally,
      publishes to pdm-features and caches in Redis
    - BATCH: triggered by TRAIN commands, fetches full history from
      ThingsBoard API, computes batch features, publishes all rows
    """

    def __init__(
        self,
        bootstrap_servers: str,
        schema_registry_url: str,
        redis_url: str,
        raw_topic: str,
        features_topic: str,
        consumer_group: str,
        schema_dir: Path,
        registry: dict | None = None,
    ) -> None:
        self._registry = registry or load_registry()
        self._engine = FeatureEngine(self._registry)
        self._cache = FeatureCache(
            redis_url,
            prefix=self._registry["redis"]["feature_prefix"].replace(":{device_id}", ""),
            ttl=self._registry["redis"]["feature_ttl_seconds"],
        )
        self._raw_topic = raw_topic
        self._features_topic = features_topic
        self._producer = self._build_producer(bootstrap_servers, schema_registry_url, schema_dir)
        self._consumer = self._build_consumer(
            bootstrap_servers, schema_registry_url, consumer_group, schema_dir
        )

    def run(self) -> None:
        self._consumer.subscribe([self._raw_topic])
        logger.info(
            f"Feature worker subscribed to {self._raw_topic}, "
            f"publishing to {self._features_topic}"
        )
        try:
            while True:
                msg = self._consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    logger.error(f"Kafka error: {msg.error()}")
                    continue
                self._handle_raw_telemetry(msg.value())
                self._consumer.commit(msg)
        except KeyboardInterrupt:
            logger.info("Feature worker shutting down")
        finally:
            self._consumer.close()
            self._producer.flush()

    def _handle_raw_telemetry(self, record: dict[str, Any] | None) -> None:
        if record is None:
            return
        device_id = str(record.get("deviceId", ""))
        ts_str = record.get("timestamp")
        values = record.get("values") or {}

        if not device_id or not values:
            return

        ts = (
            datetime.fromisoformat(ts_str)
            if ts_str
            else datetime.now(tz=timezone.utc)
        )

        features = self._engine.update_telemetry(device_id, ts, values)
        if features is None:
            return

        error_counts = self._engine.get_error_counts(device_id)
        features.update(error_counts)

        self._cache.put(device_id, features, ts)
        self._publish_features(device_id, ts, features)

    def _publish_features(
        self, device_id: str, ts: datetime, features: dict[str, float]
    ) -> None:
        event = {
            "deviceId": device_id,
            "timestamp": ts.isoformat(),
            "features": features,
            "featureColumns": self._engine.feature_columns,
        }
        self._producer.produce(
            topic=self._features_topic,
            key=device_id,
            value=event,
            on_delivery=self._delivery_report,
        )
        self._producer.poll(0)

    def _delivery_report(self, err, msg) -> None:
        if err is not None:
            logger.error(f"Failed to publish features: {err}")

    def _build_consumer(
        self,
        bootstrap_servers: str,
        schema_registry_url: str,
        consumer_group: str,
        schema_dir: Path,
    ):
        from confluent_kafka import DeserializingConsumer
        from confluent_kafka.schema_registry import SchemaRegistryClient
        from confluent_kafka.schema_registry.avro import AvroDeserializer
        from confluent_kafka.serialization import StringDeserializer

        registry_client = SchemaRegistryClient({"url": schema_registry_url})
        return DeserializingConsumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": consumer_group,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
                "key.deserializer": StringDeserializer("utf_8"),
                "value.deserializer": AvroDeserializer(registry_client),
            }
        )

    def _build_producer(
        self,
        bootstrap_servers: str,
        schema_registry_url: str,
        schema_dir: Path,
    ):
        from confluent_kafka import SerializingProducer
        from confluent_kafka.schema_registry import SchemaRegistryClient
        from confluent_kafka.schema_registry.avro import AvroSerializer
        from confluent_kafka.serialization import StringSerializer

        registry_client = SchemaRegistryClient({"url": schema_registry_url})
        return SerializingProducer(
            {
                "bootstrap.servers": bootstrap_servers,
                "key.serializer": StringSerializer("utf_8"),
                "value.serializer": AvroSerializer(registry_client),
            }
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import os

    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    schema_reg = os.getenv("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    raw_topic = os.getenv("PDM_RAW_TOPIC", "pdm-raw-telemetry")
    features_topic = os.getenv("PDM_FEATURES_TOPIC", "pdm-features")
    consumer_group = os.getenv("PDM_FEATURE_WORKER_GROUP", "pdm-feature-workers")
    schema_dir = Path(os.getenv("PDM_AVRO_SCHEMA_DIR", str(_SCHEMA_DIR)))
    registry_path = os.getenv("PDM_FEATURE_REGISTRY", str(_REGISTRY_PATH))

    registry = load_registry(Path(registry_path))

    worker = FeatureWorker(
        bootstrap_servers=bootstrap,
        schema_registry_url=schema_reg,
        redis_url=redis_url,
        raw_topic=raw_topic,
        features_topic=features_topic,
        consumer_group=consumer_group,
        schema_dir=schema_dir,
        registry=registry,
    )
    worker.run()


if __name__ == "__main__":
    main()
