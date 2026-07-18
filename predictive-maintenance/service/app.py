"""
pdm-model-store — stateless Kafka microservice.

Consumes SAVE / LOAD / DELETE / LIST / EXISTS commands from
``pdm-storage-commands``, persists artifacts to MinIO (primary) with
PostgreSQL bytea fallback, and publishes responses to
``pdm-storage-responses``.

Stateless: no local filesystem state.  Horizontal scaling via Kafka
consumer groups.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

from confluent_kafka import Consumer, Producer
from confluent_kafka.avro import AvroConsumer, AvroProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("pdm-model-store")

running = True


def _shutdown(sig, frame):
    global running
    logger.info("Received signal %s, shutting down", sig)
    running = False


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)

# ---------------------------------------------------------------------------
# Settings from environment
# ---------------------------------------------------------------------------
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")
SCHEMA_DIR = Path(os.getenv("PDM_AVRO_SCHEMA_DIR", "/app/tb-quarkus/gateway/src/main/avro"))
COMMAND_TOPIC = os.getenv("PDM_STORAGE_COMMAND_TOPIC", "pdm-storage-commands")
RESPONSE_TOPIC = os.getenv("PDM_STORAGE_RESPONSE_TOPIC", "pdm-storage-responses")
CONSUMER_GROUP = os.getenv("PDM_STORAGE_GROUP", "pdm-model-store-workers")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "pdm-models")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

PG_DSN = os.getenv(
    "MODEL_STORAGE_PG_DSN",
    "postgresql://postgres:postgres@postgres:5432/thingsboard",
)

# ---------------------------------------------------------------------------
# Storage backends (in-process, only used by this microservice)
# ---------------------------------------------------------------------------


class MinIOBackend:
    def __init__(self):
        import boto3
        from botocore.config import Config as BotoConfig

        self._client = boto3.client(
            "s3",
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            region_name="us-east-1",
            config=BotoConfig(s3={"addressing_style": "path"}),
            use_ssl=MINIO_SECURE,
        )
        self._bucket = MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            self._client.create_bucket(Bucket=self._bucket)
            logger.info("Created bucket %s", self._bucket)

    def put(self, model_id: str, filename: str, data: bytes):
        self._client.put_object(Bucket=self._bucket, Key=f"{model_id}/{filename}", Body=data)

    def get(self, model_id: str, filename: str) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=f"{model_id}/{filename}")
        return resp["Body"].read()

    def delete(self, model_id: str, filename: str):
        self._client.delete_object(Bucket=self._bucket, Key=f"{model_id}/{filename}")

    def list_files(self, model_id: str) -> list[str]:
        resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=f"{model_id}/")
        prefix = f"{model_id}/"
        return [o["Key"][len(prefix):] for o in resp.get("Contents", []) if o["Key"] != prefix]

    def exists(self, model_id: str, filename: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=f"{model_id}/{filename}")
            return True
        except Exception:
            return False


class PostgresBackend:
    def __init__(self):
        import psycopg2

        self._dsn = PG_DSN
        self._table = "pdm_model_artifacts"
        self._conn = psycopg2.connect(self._dsn)
        self._ensure_table()

    def _ensure_table(self):
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

    def put(self, model_id: str, filename: str, data: bytes):
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

    def get(self, model_id: str, filename: str) -> bytes:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT data FROM {self._table} WHERE model_id = %s AND filename = %s",
                (model_id, filename),
            )
            row = cur.fetchone()
            if row is None:
                raise FileNotFoundError(f"Not found: {model_id}/{filename}")
            return row[0]

    def delete(self, model_id: str, filename: str):
        with self._conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {self._table} WHERE model_id = %s AND filename = %s",
                (model_id, filename),
            )
            self._conn.commit()

    def list_files(self, model_id: str) -> list[str]:
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


# ---------------------------------------------------------------------------
# Fallback orchestration
# ---------------------------------------------------------------------------


class StorageOrchestrator:
    def __init__(self):
        self._minio: MinIOBackend | None = None
        self._pg: PostgresBackend | None = None
        self._init_backends()

    def _init_backends(self):
        try:
            self._minio = MinIOBackend()
            logger.info("MinIO backend ready")
        except Exception as exc:
            logger.warning("MinIO init failed: %s", exc)
        try:
            self._pg = PostgresBackend()
            logger.info("PostgreSQL backend ready")
        except Exception as exc:
            logger.warning("PostgreSQL init failed: %s", exc)

    def _try_put(self, model_id, filename, data):
        for backend in (self._minio, self._pg):
            if backend is None:
                continue
            try:
                backend.put(model_id, filename, data)
                return True
            except Exception as exc:
                logger.warning("PUT failed on %s: %s", type(backend).__name__, exc)
        return False

    def _try_get(self, model_id, filename) -> bytes | None:
        for backend in (self._minio, self._pg):
            if backend is None:
                continue
            try:
                return backend.get(model_id, filename)
            except Exception:
                continue
        return None

    def _try_delete(self, model_id, filename):
        for backend in (self._minio, self._pg):
            if backend is None:
                continue
            try:
                backend.delete(model_id, filename)
            except Exception:
                pass

    def _try_list(self, model_id) -> list[str]:
        for backend in (self._minio, self._pg):
            if backend is None:
                continue
            try:
                files = backend.list_files(model_id)
                if files:
                    return files
            except Exception:
                continue
        return []

    def _try_exists(self, model_id, filename) -> bool:
        for backend in (self._minio, self._pg):
            if backend is None:
                continue
            try:
                if backend.exists(model_id, filename):
                    return True
            except Exception:
                continue
        return False

    def handle(self, cmd: dict) -> dict:
        op = cmd["op"]
        model_id = cmd["modelId"]
        correlation_id = cmd["correlationId"]
        ts = cmd["timestamp"]

        try:
            if op == "SAVE":
                file_data = cmd.get("fileData") or {}
                ok = True
                for fname, blob in file_data.items():
                    if not self._try_put(model_id, fname, blob):
                        ok = False
                return {
                    "correlationId": correlation_id,
                    "modelId": model_id,
                    "success": ok,
                    "error": None if ok else "Some artifacts failed to persist",
                    "filenames": list(file_data.keys()),
                    "fileData": None,
                    "timestamp": ts,
                }

            if op == "LOAD":
                filenames = cmd.get("filenames") or []
                result_data: dict[str, bytes] = {}
                missing = []
                for fname in filenames:
                    blob = self._try_get(model_id, fname)
                    if blob is not None:
                        result_data[fname] = blob
                    else:
                        missing.append(fname)
                success = len(missing) == 0
                return {
                    "correlationId": correlation_id,
                    "modelId": model_id,
                    "success": success,
                    "error": f"Missing: {missing}" if missing else None,
                    "filenames": list(result_data.keys()),
                    "fileData": result_data,
                    "timestamp": ts,
                }

            if op == "DELETE":
                filenames = cmd.get("filenames") or []
                for fname in filenames:
                    self._try_delete(model_id, fname)
                return {
                    "correlationId": correlation_id,
                    "modelId": model_id,
                    "success": True,
                    "error": None,
                    "filenames": filenames,
                    "fileData": None,
                    "timestamp": ts,
                }

            if op == "LIST":
                files = self._try_list(model_id)
                return {
                    "correlationId": correlation_id,
                    "modelId": model_id,
                    "success": True,
                    "error": None,
                    "filenames": files,
                    "fileData": None,
                    "timestamp": ts,
                }

            if op == "EXISTS":
                filenames = cmd.get("filenames") or []
                found = [f for f in filenames if self._try_exists(model_id, f)]
                return {
                    "correlationId": correlation_id,
                    "modelId": model_id,
                    "success": True,
                    "error": None,
                    "filenames": found,
                    "fileData": None,
                    "timestamp": ts,
                }

            return {
                "correlationId": correlation_id,
                "modelId": model_id,
                "success": False,
                "error": f"Unknown op: {op}",
                "filenames": None,
                "fileData": None,
                "timestamp": ts,
            }

        except Exception as exc:
            logger.exception("Error handling %s for %s", op, model_id)
            return {
                "correlationId": correlation_id,
                "modelId": model_id,
                "success": False,
                "error": str(exc),
                "filenames": None,
                "fileData": None,
                "timestamp": ts,
            }


# ---------------------------------------------------------------------------
# Kafka setup
# ---------------------------------------------------------------------------


def build_schema_registry() -> SchemaRegistryClient:
    return SchemaRegistryClient({"url": SCHEMA_REGISTRY_URL})


def build_producer(sr: SchemaRegistryClient) -> Producer:
    resp_schema_str = (SCHEMA_DIR / "pdm-storage-responses-value.avsc").read_text(encoding="utf-8")
    return AvroProducer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "acks": "all",
        },
        schema_registry=sr,
        default_value_schema=resp_schema_str,
    )


def build_consumer(sr: SchemaRegistryClient) -> AvroConsumer:
    cmd_schema_str = (SCHEMA_DIR / "pdm-storage-commands-value.avsc").read_text(encoding="utf-8")
    return AvroConsumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": CONSUMER_GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        },
        schema_registry=sr,
        reader_value_schema=cmd_schema_str,
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main():
    sr = build_schema_registry()
    producer = build_producer(sr)
    consumer = build_consumer(sr)
    consumer.subscribe([COMMAND_TOPIC])

    orchestrator = StorageOrchestrator()
    logger.info(
        "pdm-model-store started — listening on %s, replying to %s",
        COMMAND_TOPIC,
        RESPONSE_TOPIC,
    )

    while running:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            logger.error("Consumer error: %s", msg.error())
            continue

        cmd = msg.value()
        if cmd is None:
            continue

        logger.info(
            "Received %s for modelId=%s corr=%s",
            cmd.get("op"),
            cmd.get("modelId"),
            cmd.get("correlationId"),
        )

        response = orchestrator.handle(cmd)

        try:
            producer.produce(
                topic=RESPONSE_TOPIC,
                key=msg.key(),
                value=response,
            )
            producer.flush()
        except Exception as exc:
            logger.exception("Failed to produce response for %s", cmd.get("correlationId"))

        consumer.commit(msg)

    consumer.close()
    logger.info("pdm-model-store stopped")


if __name__ == "__main__":
    main()
