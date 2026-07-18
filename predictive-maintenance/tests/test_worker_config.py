import os
from pathlib import Path

from src.pdm_worker.config import WorkerConfig, load_config


class TestWorkerConfig:
    def test_load_config_defaults(self):
        env_keys = [
            "KAFKA_BOOTSTRAP_SERVERS", "SCHEMA_REGISTRY_URL", "REDIS_URL",
            "PDM_COMMAND_TOPIC", "PDM_EVENT_TOPIC", "PDM_WORKER_GROUP",
            "PDM_WORKER_MODEL_TYPE", "PDM_AVRO_SCHEMA_DIR",
        ]
        saved = {k: os.environ.pop(k, None) for k in env_keys}
        try:
            config = load_config()
            assert config.kafka_bootstrap_servers == "kafka:9092"
            assert config.schema_registry_url == "http://schema-registry:8081"
            assert config.redis_url == "redis://redis:6379/0"
            assert config.command_topic == "pdm-commands"
            assert config.event_topic == "pdm-events"
            assert config.worker_model_type == "FORECAST"
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_load_config_custom(self):
        env_overrides = {
            "KAFKA_BOOTSTRAP_SERVERS": "custom-kafka:9092",
            "PDM_WORKER_MODEL_TYPE": "ANOMALY",
        }
        saved = {k: os.environ.pop(k, None) for k in env_overrides}
        try:
            os.environ.update(env_overrides)
            config = load_config()
            assert config.kafka_bootstrap_servers == "custom-kafka:9092"
            assert config.worker_model_type == "ANOMALY"
        finally:
            for k in env_overrides:
                os.environ.pop(k, None)
                if saved[k] is not None:
                    os.environ[k] = saved[k]

    def test_config_is_frozen(self):
        config = WorkerConfig(
            kafka_bootstrap_servers="k:9092",
            schema_registry_url="http://sr:8081",
            redis_url="redis://r:6379/0",
            command_topic="cmd",
            event_topic="evt",
            consumer_group="grp",
            worker_model_type="FORECAST",
            schema_dir=Path("/tmp"),
        )
        import pytest
        with pytest.raises(AttributeError):
            config.kafka_bootstrap_servers = "new"
