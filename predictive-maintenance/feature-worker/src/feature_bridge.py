"""Bridge between existing DataRegistry/AnomalyPredictor and the shared FeatureEngine.

Drop-in replacement: imports the same function signatures, delegates to FeatureEngine
for batch computation, and optionally reads pre-computed features from Redis cache.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

_file_path = Path(__file__).resolve()
_predictive_maintenance_path = _file_path.parent.parent.parent
if str(_predictive_maintenance_path) not in sys.path:
    sys.path.insert(0, str(_predictive_maintenance_path))

try:
    from feature_worker.src.feature_worker import FeatureEngine, load_registry
    from feature_worker.src.cache_client import FeatureCacheClient
except ImportError:
    from src.feature_worker import FeatureEngine, load_registry  # type: ignore[no-redef]
    from src.cache_client import FeatureCacheClient  # type: ignore[no-redef]

from src.logger import logger

_registry = load_registry()
_engine = FeatureEngine(_registry)

_cache: FeatureCacheClient | None = None


def _get_cache() -> FeatureCacheClient | None:
    global _cache
    if _cache is None:
        import os

        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        _cache = FeatureCacheClient(redis_url)
    return _cache


def get_feature_engine() -> FeatureEngine:
    return _engine


def compute_anomaly_features_batch(
    telemetry_df: pd.DataFrame,
    errors_df: pd.DataFrame | None,
    maintenance_df: pd.DataFrame | None,
    machines_df: pd.DataFrame | None,
) -> pd.DataFrame:
    """Batch feature computation replacing the inline create_* functions in anomaly_predictor.py."""
    return _engine.compute_batch_features(telemetry_df, errors_df, maintenance_df, machines_df)


def fetch_cached_features(device_id: str) -> dict[str, float] | None:
    """Read pre-computed features from Redis cache (used by inference workers)."""
    cache = _get_cache()
    if cache is None:
        return None
    return cache.get_features(device_id)


def fetch_cached_features_or_compute(
    device_id: str,
    telemetry_df: pd.DataFrame,
    errors_df: pd.DataFrame | None = None,
    maintenance_df: pd.DataFrame | None = None,
    machines_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Try Redis cache first, fall back to batch computation."""
    cached = fetch_cached_features(device_id)
    if cached is not None:
        logger.info(f"Using cached features for device {device_id}")
        return pd.DataFrame([cached])

    logger.info(f"Cache miss for device {device_id}, computing batch features")
    return compute_anomaly_features_batch(
        telemetry_df, errors_df, maintenance_df, machines_df
    )
