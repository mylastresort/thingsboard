import os
from typing import List, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "predictive-maintenance"
    app_description: str = "Predictive Maintenance Service"
    app_version: str = "0.1.0"
    app_debug: bool = False
    app_root_path: str = "/api/v1"
    cors_origins: Union[List[str], str] = os.getenv(
        "CORS_ORIGINS", "http://thingsboard:8080,http://thingsboard:4200"
    )
    models_path: str = os.getenv("MODELS_PATH", "/app/models")

    # Model storage backend: "minio" | "postgres" | "local"
    model_storage_strategy: str = os.getenv("MODEL_STORAGE_STRATEGY", "minio")

    # MinIO settings
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "pdm-models")
    minio_secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"

    # PostgreSQL model storage DSN (fallback backend)
    model_storage_pg_dsn: str = os.getenv(
        "MODEL_STORAGE_PG_DSN",
        "postgresql://postgres:postgres@postgres:5432/thingsboard",
    )

    # Telemetry configuration for predictive maintenance
    telemetry_keys: Union[List[str], str] = ["volt", "rotate", "pressure", "vibration"]
    error_keys: Union[List[str], str] = [
        "error1",
        "error2",
        "error3",
        "error4",
        "error5",
    ]
    component_keys: Union[List[str], str] = ["comp1", "comp2", "comp3", "comp4"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[List[str], str]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("telemetry_keys", "error_keys", "component_keys", mode="before")
    @classmethod
    def parse_list_config(cls, v: Union[List[str], str]) -> List[str]:
        if isinstance(v, str):
            return [key.strip() for key in v.split(",") if key.strip()]
        return v


settings = Settings()
