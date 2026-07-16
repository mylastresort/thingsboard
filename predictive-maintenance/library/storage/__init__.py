"""
Kafka-based client for the pdm-model-store microservice.

Workers use this to publish SAVE / LOAD / DELETE / LIST / EXISTS
commands to ``pdm-storage-commands`` and block until the matching
response arrives on ``pdm-storage-responses``.

Stateless — all persistence lives in the model-store service.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from confluent_kafka import Consumer, Producer
from confluent_kafka.avro import AvroConsumer, AvroProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")
SCHEMA_DIR = Path(os.getenv("PDM_AVRO_SCHEMA_DIR", "/app/tb-quarkus/gateway/src/main/avro"))
COMMAND_TOPIC = os.getenv("PDM_STORAGE_COMMAND_TOPIC", "pdm-storage-commands")
RESPONSE_TOPIC = os.getenv("PDM_STORAGE_RESPONSE_TOPIC", "pdm-storage-responses")

_DEFAULT_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------

_sr: SchemaRegistryClient | None = None
_producer: AvroProducer | None = None
_consumer: AvroConsumer | None = None
_consumer_lock = threading.Lock()
_pending: dict[str, threading.Event] = {}
_responses: dict[str, dict] = {}
_response_lock = threading.Lock()


def _get_sr() -> SchemaRegistryClient:
    global _sr
    if _sr is None:
        _sr = SchemaRegistryClient({"url": SCHEMA_REGISTRY_URL})
    return _sr


def _get_producer() -> AvroProducer:
    global _producer
    if _producer is None:
        sr = _get_sr()
        schema_str = (SCHEMA_DIR / "pdm-storage-commands-value.avsc").read_text(encoding="utf-8")
        _producer = AvroProducer(
            {"bootstrap.servers": KAFKA_BOOTSTRAP, "acks": "all"},
            schema_registry=sr,
            default_value_schema=schema_str,
        )
    return _producer


def _get_consumer() -> AvroConsumer:
    global _consumer
    if _consumer is None:
        sr = _get_sr()
        schema_str = (SCHEMA_DIR / "pdm-storage-responses-value.avsc").read_text(encoding="utf-8")
        _consumer = AvroConsumer(
            {
                "bootstrap.servers": KAFKA_BOOTSTRAP,
                "group.id": f"pdm-worker-{uuid.uuid4().hex[:8]}",
                "auto.offset.reset": "latest",
                "enable.auto.commit": True,
            },
            schema_registry=sr,
            schema=schema_str,
        )
        _consumer.subscribe([RESPONSE_TOPIC])
    return _consumer


_response_thread: threading.Thread | None = None
_response_thread_lock = threading.Lock()


def _ensure_response_listener():
    """Start a single daemon thread that drains the response topic."""
    global _response_thread
    if _response_thread is not None and _response_thread.is_alive():
        return
    with _response_thread_lock:
        if _response_thread is not None and _response_thread.is_alive():
            return
        _response_thread = threading.Thread(target=_drain_responses, daemon=True)
        _response_thread.start()


def _drain_responses():
    consumer = _get_consumer()
    while True:
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        resp = msg.value()
        if resp is None:
            continue
        cid = resp["correlationId"]
        with _response_lock:
            _responses[cid] = resp
        event = _pending.pop(cid, None)
        if event:
            event.set()


# ---------------------------------------------------------------------------
# Public API — blocking, used by workers
# ---------------------------------------------------------------------------


def _send_and_wait(cmd: dict, timeout: float = _DEFAULT_TIMEOUT) -> dict:
    correlation_id = cmd["correlationId"]

    event = threading.Event()
    with _response_lock:
        _pending[correlation_id] = event
    _ensure_response_listener()

    producer = _get_producer()
    model_id = cmd["modelId"]
    producer.produce(
        topic=COMMAND_TOPIC,
        key=model_id,
        value=cmd,
    )
    producer.flush()

    if not event.wait(timeout=timeout):
        with _response_lock:
            _pending.pop(correlation_id, None)
        raise TimeoutError(f"No response for {cmd['op']} modelId={model_id} corr={correlation_id}")

    with _response_lock:
        return _responses.pop(correlation_id)


def save_model(model_id: str, model_dir: Path, timeout: float = _DEFAULT_TIMEOUT) -> bool:
    """Save all files in *model_dir* to the storage microservice."""
    model_dir = Path(model_dir)
    if not model_dir.is_dir():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    file_data: Dict[str, bytes] = {}
    for artifact in model_dir.iterdir():
        if artifact.is_file():
            file_data[artifact.name] = artifact.read_bytes()

    resp = _send_and_wait(
        {
            "op": "SAVE",
            "modelId": model_id,
            "correlationId": uuid.uuid4().hex,
            "filenames": list(file_data.keys()),
            "fileData": file_data,
            "timestamp": int(time.time() * 1000),
        },
        timeout=timeout,
    )
    if not resp["success"]:
        logger.error("save_model failed: %s", resp.get("error"))
    return resp["success"]


def load_model(
    model_id: str,
    target_dir: Path,
    filenames: List[str] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> Path:
    """Load model artifacts into *target_dir* from the storage microservice."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if filenames is None:
        resp = _send_and_wait(
            {
                "op": "LIST",
                "modelId": model_id,
                "correlationId": uuid.uuid4().hex,
                "filenames": None,
                "fileData": None,
                "timestamp": int(time.time() * 1000),
            },
            timeout=timeout,
        )
        filenames = resp.get("filenames") or []
        if not filenames:
            raise FileNotFoundError(f"No artifacts for model {model_id}")

    resp = _send_and_wait(
        {
            "op": "LOAD",
            "modelId": model_id,
            "correlationId": uuid.uuid4().hex,
            "filenames": filenames,
            "fileData": None,
            "timestamp": int(time.time() * 1000),
        },
        timeout=timeout,
    )

    if not resp["success"]:
        raise FileNotFoundError(f"Load failed for {model_id}: {resp.get('error')}")

    file_data = resp.get("fileData") or {}
    for fname, blob in file_data.items():
        (target_dir / fname).write_bytes(blob)

    logger.info("Loaded model %s into %s (%d files)", model_id, target_dir, len(file_data))
    return target_dir


def delete_model(model_id: str, timeout: float = _DEFAULT_TIMEOUT) -> bool:
    """Delete a model from all backends."""
    resp = _send_and_wait(
        {
            "op": "DELETE",
            "modelId": model_id,
            "correlationId": uuid.uuid4().hex,
            "filenames": None,
            "fileData": None,
            "timestamp": int(time.time() * 1000),
        },
        timeout=timeout,
    )
    return resp["success"]


def list_files(model_id: str, timeout: float = _DEFAULT_TIMEOUT) -> List[str]:
    """List all artifact filenames for a model."""
    resp = _send_and_wait(
        {
            "op": "LIST",
            "modelId": model_id,
            "correlationId": uuid.uuid4().hex,
            "filenames": None,
            "fileData": None,
            "timestamp": int(time.time() * 1000),
        },
        timeout=timeout,
    )
    return resp.get("filenames") or []


def exists(model_id: str, filenames: List[str], timeout: float = _DEFAULT_TIMEOUT) -> List[str]:
    """Return subset of *filenames* that exist in storage."""
    resp = _send_and_wait(
        {
            "op": "EXISTS",
            "modelId": model_id,
            "correlationId": uuid.uuid4().hex,
            "filenames": filenames,
            "fileData": None,
            "timestamp": int(time.time() * 1000),
        },
        timeout=timeout,
    )
    return resp.get("filenames") or []
