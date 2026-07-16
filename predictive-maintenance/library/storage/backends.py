"""
Storage backends for PdM model artifacts.

Provides an abstract ModelStorageBackend and concrete implementations:
  - MinIOStorageBackend: S3-compatible object storage (default).
  - PostgresStorageBackend: stores binary blobs in PostgreSQL.
  - LocalStorageBackend: local filesystem (legacy fallback).
"""

from __future__ import annotations

import io
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, List, Optional

logger = logging.getLogger(__name__)


class ModelStorageBackend(ABC):
    """Abstract base for model storage backends."""

    @abstractmethod
    def put(self, model_id: str, filename: str, data: bytes) -> str:
        """Store a model artifact. Returns the object key / path."""

    @abstractmethod
    def get(self, model_id: str, filename: str) -> bytes:
        """Retrieve a model artifact by key."""

    @abstractmethod
    def delete(self, model_id: str, filename: str) -> None:
        """Delete a model artifact."""

    @abstractmethod
    def list_files(self, model_id: str) -> List[str]:
        """List all artifact filenames for a model."""

    @abstractmethod
    def exists(self, model_id: str, filename: str) -> bool:
        """Check if an artifact exists."""


class MinIOStorageBackend(ModelStorageBackend):
    """S3-compatible object storage backend using MinIO / boto3."""

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str = "pdm-models",
        region: str = "us-east-1",
        secure: bool = False,
    ) -> None:
        from botocore.config import Config as BotoConfig

        import boto3

        self._endpoint = endpoint or os.getenv(
            "MINIO_ENDPOINT", "http://minio:9000"
        )
        self._bucket = bucket or os.getenv("MINIO_BUCKET", "pdm-models")
        self._ak = access_key or os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self._sk = secret_key or os.getenv("MINIO_SECRET_KEY", "minioadmin")

        self._client = boto3.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._ak,
            aws_secret_access_key=self._sk,
            region_name=region,
            config=BotoConfig(s3={"addressing_style": "path"}),
            use_ssl=secure,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            self._client.create_bucket(Bucket=self._bucket)
            logger.info("Created MinIO bucket %s", self._bucket)

    def _key(self, model_id: str, filename: str) -> str:
        return f"{model_id}/{filename}"

    def put(self, model_id: str, filename: str, data: bytes) -> str:
        key = self._key(model_id, filename)
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        logger.debug("PUT s3://%s/%s (%d bytes)", self._bucket, key, len(data))
        return key

    def get(self, model_id: str, filename: str) -> bytes:
        key = self._key(model_id, filename)
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    def delete(self, model_id: str, filename: str) -> None:
        key = self._key(model_id, filename)
        self._client.delete_object(Bucket=self._bucket, Key=key)
        logger.debug("DELETE s3://%s/%s", self._bucket, key)

    def list_files(self, model_id: str) -> List[str]:
        prefix = f"{model_id}/"
        resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        return [
            obj["Key"][len(prefix) :]
            for obj in resp.get("Contents", [])
            if obj["Key"] != prefix
        ]

    def exists(self, model_id: str, filename: str) -> bool:
        key = self._key(model_id, filename)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False


class PostgresStorageBackend(ModelStorageBackend):
    """Stores model artifacts as bytea blobs in PostgreSQL."""

    def __init__(
        self,
        dsn: str | None = None,
        table: str = "pdm_model_artifacts",
    ) -> None:
        import psycopg2

        self._dsn = dsn or os.getenv(
            "MODEL_STORAGE_PG_DSN",
            "postgresql://postgres:postgres@postgres:5432/thingsboard",
        )
        self._table = table
        self._conn = psycopg2.connect(self._dsn)
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    model_id   TEXT NOT NULL,
                    filename   TEXT NOT NULL,
                    data       BYTEA NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    PRIMARY KEY (model_id, filename)
                )
                """
            )
            self._conn.commit()

    def put(self, model_id: str, filename: str, data: bytes) -> str:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {self._table} (model_id, filename, data)
                VALUES (%s, %s, %s)
                ON CONFLICT (model_id, filename)
                DO UPDATE SET data = EXCLUDED.data
                """,
                (model_id, filename, data),
            )
            self._conn.commit()
        logger.debug(
            "PUT pg://%s/%s/%s (%d bytes)", self._table, model_id, filename, len(data)
        )
        return f"{model_id}/{filename}"

    def get(self, model_id: str, filename: str) -> bytes:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT data FROM {self._table} WHERE model_id = %s AND filename = %s",
                (model_id, filename),
            )
            row = cur.fetchone()
            if row is None:
                raise FileNotFoundError(
                    f"Artifact not found: {model_id}/{filename}"
                )
            return row[0]

    def delete(self, model_id: str, filename: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {self._table} WHERE model_id = %s AND filename = %s",
                (model_id, filename),
            )
            self._conn.commit()
        logger.debug("DELETE pg://%s/%s/%s", self._table, model_id, filename)

    def list_files(self, model_id: str) -> List[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT filename FROM {self._table} WHERE model_id = %s",
                (model_id,),
            )
            return [row[0] for row in cur.fetchall()]

    def exists(self, model_id: str, filename: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT 1 FROM {self._table} WHERE model_id = %s AND filename = %s",
                (model_id, filename),
            )
            return cur.fetchone() is not None


class LocalStorageBackend(ModelStorageBackend):
    """Local filesystem backend (legacy / dev fallback)."""

    def __init__(self, root: str | None = None) -> None:
        self._root = Path(root or os.getenv("MODELS_PATH", "/app/models"))
        self._root.mkdir(parents=True, exist_ok=True)

    def _dir(self, model_id: str) -> Path:
        d = self._root / model_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def put(self, model_id: str, filename: str, data: bytes) -> str:
        p = self._dir(model_id) / filename
        p.write_bytes(data)
        logger.debug("PUT local://%s (%d bytes)", p, len(data))
        return str(p)

    def get(self, model_id: str, filename: str) -> bytes:
        p = self._dir(model_id) / filename
        if not p.exists():
            raise FileNotFoundError(f"Artifact not found: {p}")
        return p.read_bytes()

    def delete(self, model_id: str, filename: str) -> None:
        p = self._dir(model_id) / filename
        if p.exists():
            p.unlink()
        logger.debug("DELETE local://%s", p)

    def list_files(self, model_id: str) -> List[str]:
        d = self._dir(model_id)
        return [f.name for f in d.iterdir() if f.is_file()]

    def exists(self, model_id: str, filename: str) -> bool:
        return (self._dir(model_id) / filename).exists()
