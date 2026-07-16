"""PdM worker observability: Prometheus metrics endpoint + health check HTTP server.

Runs a lightweight threading-based HTTP server on a configurable port
that exposes /metrics (Prometheus exposition format) and /health (JSON).
No external dependencies beyond the stdlib and ``prometheus_client``.

Usage from worker.py::

    from src.pdm_worker.observability import start_observability_server

    server = start_observability_server(port=8100)
    # server is a background daemon thread; metrics update automatically.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

if TYPE_CHECKING:
    from src.pdm_worker.worker import PdmKafkaWorker

REGISTRY = CollectorRegistry(auto_describe=True)

# ── Metrics ───────────────────────────────────────────────────────────────────

commands_received = Counter(
    "pdm_commands_received_total",
    "Total PDM commands received from Kafka",
    ["command_type", "model_type"],
    registry=REGISTRY,
)

commands_processed = Counter(
    "pdm_commands_processed_total",
    "Total PDM commands processed successfully",
    ["command_type", "model_type"],
    registry=REGISTRY,
)

command_duration_seconds = Histogram(
    "pdm_command_duration_seconds",
    "Time spent processing a PDM command",
    ["command_type"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)

kafka_polls_total = Counter(
    "pdm_kafka_polls_total",
    "Total Kafka poll() calls",
    ["result"],
    registry=REGISTRY,
)

active_jobs = Gauge(
    "pdm_active_jobs",
    "Number of currently active PDM jobs",
    ["model_type"],
    registry=REGISTRY,
)

training_in_progress = Gauge(
    "pdm_training_in_progress",
    "Whether a training job is currently running (1=yes, 0=no)",
    registry=REGISTRY,
)

worker_start_time = Gauge(
    "pdm_worker_start_time_seconds",
    "Unix timestamp when the worker started",
    registry=REGISTRY,
)

worker_uptime_seconds = Gauge(
    "pdm_worker_uptime_seconds",
    "Seconds since the worker started",
    registry=REGISTRY,
)

kafka_connected = Gauge(
    "pdm_kafka_connected",
    "Whether the Kafka consumer is connected (1=yes, 0=no)",
    registry=REGISTRY,
)

redis_connected = Gauge(
    "pdm_redis_connected",
    "Whether Redis is reachable (1=yes, 0=no)",
    registry=REGISTRY,
)


def _uptime() -> float:
    return round(time.time() - _start_ts, 1)


worker_uptime_seconds.set_function(_uptime)


# ── HTTP Server ───────────────────────────────────────────────────────────────

class _MetricsHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for /metrics and /health."""

    server_version = "PdM-Worker/1.0"

    def do_GET(self) -> None:  # noqa: N802 – HTTP method naming
        if self.path == "/metrics":
            self._respond(200, "text/plain; version=0.0.4; charset=utf-8", generate_latest(REGISTRY))
        elif self.path == "/health":
            body = json.dumps({
                "status": "UP",
                "worker_model_type": os.getenv("PDM_WORKER_MODEL_TYPE", "UNKNOWN"),
                "uptime_seconds": round(time.time() - _start_ts, 1),
            }).encode()
            self._respond(200, "application/json", body)
        else:
            self._respond(404, "text/plain", b"Not Found")

    def _respond(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: D401
        """Suppress default stderr request logging."""
        pass  # silence access logs in production


_start_ts = time.time()


def _run_server(port: int) -> None:
    httpd = HTTPServer(("0.0.0.0", port), _MetricsHandler)
    httpd.serve_forever()


def start_observability_server(port: int = 8100) -> threading.Thread:
    """Start the metrics/health HTTP server in a daemon thread.

    Returns the thread so the caller can optionally join it.
    """
    worker_start_time.set(_start_ts)
    t = threading.Thread(target=_run_server, args=(port,), daemon=True, name="observability")
    t.start()
    return t
