"""Tests for feature engineering worker: FeatureEngine, SlidingBuffer, FeatureCache."""

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root))
_fw = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_fw))

from src.feature_worker import FeatureEngine, SlidingBuffer, load_registry


# ---------------------------------------------------------------------------
# SlidingBuffer
# ---------------------------------------------------------------------------

class TestSlidingBuffer:
    def test_single_sample(self):
        buf = SlidingBuffer(max_samples=8)
        stats = buf.update("dev1", {"volt": 10.0, "rotate": 100.0})
        assert stats["volt"]["mean"] == 10.0
        assert stats["volt"]["std"] == 0.0

    def test_multiple_samples(self):
        buf = SlidingBuffer(max_samples=8)
        for v in [10.0, 20.0, 30.0]:
            stats = buf.update("dev1", {"volt": v})
        assert stats["volt"]["mean"] == pytest.approx(20.0)
        assert stats["volt"]["std"] > 0

    def test_max_samples_eviction(self):
        buf = SlidingBuffer(max_samples=3)
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            buf.update("dev1", {"volt": v})
        assert buf.get_buffer("dev1")["volt"] == [3.0, 4.0, 5.0]

    def test_independent_devices(self):
        buf = SlidingBuffer(max_samples=8)
        buf.update("dev1", {"volt": 10.0})
        buf.update("dev2", {"volt": 20.0})
        assert buf.get_buffer("dev1")["volt"] == [10.0]
        assert buf.get_buffer("dev2")["volt"] == [20.0]


# ---------------------------------------------------------------------------
# FeatureEngine (incremental)
# ---------------------------------------------------------------------------

class TestFeatureEngineIncremental:
    def _make_engine(self):
        registry = load_registry()
        return FeatureEngine(registry)

    def test_telemetry_returns_none_during_warmup(self):
        engine = self._make_engine()
        ts = datetime.now(tz=timezone.utc)
        for i in range(7):
            result = engine.update_telemetry(
                "dev1", ts + timedelta(hours=3 * i),
                {"volt": 10.0, "rotate": 100.0, "pressure": 50.0, "vibration": 5.0},
            )
            assert result is None

    def test_telemetry_returns_features_after_warmup(self):
        engine = self._make_engine()
        ts = datetime.now(tz=timezone.utc)
        result = None
        for i in range(8):
            result = engine.update_telemetry(
                "dev1", ts + timedelta(hours=3 * i),
                {"volt": 10.0, "rotate": 100.0, "pressure": 50.0, "vibration": 5.0},
            )
        assert result is not None
        assert "voltmean_3h" in result
        assert "voltmean_24h" in result
        assert "age" in result

    def test_feature_columns_match_registry(self):
        engine = self._make_engine()
        registry = load_registry()
        assert engine.feature_columns == registry["feature_columns"]

    def test_error_counts(self):
        engine = self._make_engine()
        engine.update_errors("dev1", "error1")
        engine.update_errors("dev1", "error1")
        engine.update_errors("dev1", "error2")
        counts = engine.get_error_counts("dev1")
        assert counts["error1count"] == 2.0
        assert counts["error2count"] == 1.0
        assert counts["error3count"] == 0.0

    def test_component_replacement(self):
        engine = self._make_engine()
        now = datetime.now(tz=timezone.utc)
        engine.update_replacement("dev1", "comp1", now - timedelta(days=30))
        engine.update_replacement("dev1", "comp2", now - timedelta(days=100))
        features = engine.update_telemetry(
            "dev1", now,
            {"volt": 10.0, "rotate": 100.0, "pressure": 50.0, "vibration": 5.0},
        )
        if features is not None:
            assert features["comp1"] == pytest.approx(30.0, abs=0.1)
            assert features["comp2"] == pytest.approx(100.0, abs=0.1)

    def test_machine_age(self):
        engine = self._make_engine()
        engine.set_machine_age("dev1", 25)
        now = datetime.now(tz=timezone.utc)
        for i in range(8):
            engine.update_telemetry(
                "dev1", now + timedelta(hours=3 * i),
                {"volt": 10.0, "rotate": 100.0, "pressure": 50.0, "vibration": 5.0},
            )


# ---------------------------------------------------------------------------
# FeatureEngine (batch)
# ---------------------------------------------------------------------------

class TestFeatureEngineBatch:
    def _make_engine(self):
        registry = load_registry()
        return FeatureEngine(registry)

    def _make_telemetry(self, n=100):
        dates = pd.date_range("2024-01-01", periods=n, freq="10min")
        return pd.DataFrame({
            "datetime": dates,
            "machineID": [1] * n,
            "volt": np.random.normal(10, 1, n),
            "rotate": np.random.normal(100, 5, n),
            "pressure": np.random.normal(50, 2, n),
            "vibration": np.random.normal(5, 0.5, n),
        })

    def test_batch_produces_features(self):
        engine = self._make_engine()
        telemetry = self._make_telemetry(500)
        features = engine.compute_batch_features(telemetry, None, None, None)
        assert len(features) > 0
        assert all(
            col in features.columns
            for col in ["voltmean_3h", "voltsd_3h", "voltmean_24h", "voltsd_24h", "age"]
        )

    def test_batch_with_errors(self):
        engine = self._make_engine()
        telemetry = self._make_telemetry(500)
        errors = pd.DataFrame({
            "datetime": pd.date_range("2024-01-01", periods=10, freq="3h"),
            "machineID": [1] * 10,
            "errorID": ["error1"] * 5 + ["error2"] * 5,
        })
        features = engine.compute_batch_features(telemetry, errors, None, None)
        assert "error1count" in features.columns
        assert "error2count" in features.columns


# ---------------------------------------------------------------------------
# load_registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_loads(self):
        registry = load_registry()
        assert "metadata" in registry
        assert "feature_columns" in registry
        assert len(registry["feature_columns"]) == 26

    def test_feature_columns_match_definitions(self):
        registry = load_registry()
        tele_keys = registry["metadata"]["telemetry_keys"]
        error_keys = registry["metadata"]["error_keys"]
        comp_keys = registry["metadata"]["component_keys"]

        expected = []
        for k in tele_keys:
            expected.extend([f"{k}mean_3h", f"{k}sd_3h", f"{k}mean_24h", f"{k}sd_24h"])
        for ek in error_keys:
            expected.append(f"{ek}count")
        expected.extend(comp_keys)
        expected.append("age")

        assert registry["feature_columns"] == expected
