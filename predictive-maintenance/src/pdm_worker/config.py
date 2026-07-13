import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkerConfig:
    kafka_bootstrap_servers: str
    schema_registry_url: str
    redis_url: str
    command_topic: str
    event_topic: str
    consumer_group: str
    worker_model_type: str
    schema_dir: Path


def load_config() -> WorkerConfig:
    worker_model_type = os.getenv("PDM_WORKER_MODEL_TYPE", "FORECAST").upper()
    return WorkerConfig(
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        schema_registry_url=os.getenv("SCHEMA_REGISTRY_URL", "http://schema-registry:8081"),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        command_topic=os.getenv("PDM_COMMAND_TOPIC", "pdm-commands"),
        event_topic=os.getenv("PDM_EVENT_TOPIC", "pdm-events"),
        consumer_group=os.getenv(
            "PDM_WORKER_GROUP", f"pdm-python-{worker_model_type.lower()}-workers"
        ),
        worker_model_type=worker_model_type,
        schema_dir=Path(
            os.getenv("PDM_AVRO_SCHEMA_DIR", "/app/tb-quarkus/gateway/src/main/avro")
        ),
    )
