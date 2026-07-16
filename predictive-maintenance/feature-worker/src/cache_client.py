"""Feature cache client for consuming pre-computed features from Redis.

Used by inference workers (Rust, Python) and training bridge to read
features computed by the feature worker instead of recomputing them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis


class FeatureCacheClient:
    """Read pre-computed feature vectors from Redis.

    Key pattern: pdm:features:{device_id}
    """

    def __init__(self, redis_url: str, prefix: str = "pdm:features") -> None:
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._prefix = prefix

    def get_features(self, device_id: str) -> dict[str, float] | None:
        key = f"{self._prefix}:{device_id}"
        raw = self._redis.get(key)
        if raw is None:
            return None
        return json.loads(raw).get("features")

    def get_with_timestamp(self, device_id: str) -> dict[str, Any] | None:
        key = f"{self._prefix}:{device_id}"
        raw = self._redis.get(key)
        if raw is None:
            return None
        data = json.loads(raw)
        return {
            "features": data.get("features"),
            "timestamp": data.get("timestamp"),
        }

    def get_batch(self, device_ids: list[str]) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for did in device_ids:
            features = self.get_features(did)
            if features is not None:
                result[did] = features
        return result

    def exists(self, device_id: str) -> bool:
        return self._redis.exists(f"{self._prefix}:{device_id}") > 0

    def ttl(self, device_id: str) -> int:
        return self._redis.ttl(f"{self._prefix}:{device_id}")

    def keys(self, pattern: str = "*") -> list[str]:
        return self._redis.keys(f"{self._prefix}:{pattern}")
