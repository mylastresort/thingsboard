from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from library.models.anomaly_predictor import (
    AnomalyPredictor,
    create_error_count_features,
    create_telemetry_features,
    create_and_train_hourly_models,
    predict_next_24h_hourly_failures,
    save_models,
    load_models,
    create_targets,
)
from library.core.data_registry import DataRegistry


@pytest.fixture
def mock_data_registry():
    dr = MagicMock(spec=DataRegistry)
    dr.telemetry_keys = ["volt", "rotate", "pressure", "vibration"]
    dr.error_keys = ["error1", "error2", "error3", "error4", "error5"]
    dr.component_keys = ["comp1", "comp2", "comp3", "comp4"]
    return dr


@pytest.fixture
def sample_telemetry():
    n = 500
    np.random.seed(42)
    timestamps = pd.date_range("2015-01-01", periods=n, freq="h")
    return pd.DataFrame({
        "datetime": timestamps,
        "machineID": 1,
        "volt": np.random.normal(150, 10, n),
        "rotate": np.random.normal(400, 20, n),
        "pressure": np.random.normal(90, 5, n),
        "vibration": np.random.normal(50, 5, n),
    })


@pytest.fixture
def sample_errors():
    n = 50
    np.random.seed(42)
    timestamps = pd.date_range("2015-01-01", periods=n, freq="12h")
    return pd.DataFrame({
        "datetime": timestamps,
        "machineID": 1,
        "errorID": np.random.choice(["error1", "error2", "error3", "error4", "error5"], n),
    })


@pytest.fixture
def sample_maintenance():
    n = 20
    np.random.seed(42)
    timestamps = pd.date_range("2015-01-01", periods=n, freq="3d")
    return pd.DataFrame({
        "datetime": timestamps,
        "machineID": 1,
        "comp": np.random.choice(["comp1", "comp2", "comp3", "comp4"], n),
    })


@pytest.fixture
def sample_failures():
    n = 10
    np.random.seed(42)
    timestamps = pd.date_range("2015-01-01", periods=n, freq="7d")
    return pd.DataFrame({
        "datetime": timestamps,
        "machineID": 1,
        "failure": np.random.choice(["comp1", "comp2", "comp3", "comp4", "none"], n),
    })


@pytest.fixture
def sample_machines():
    return pd.DataFrame({"machineID": [1], "age": [5], "model": ["model3"]})


class TestAnomalyPredictorInit:
    def test_init_defaults(self, mock_data_registry):
        model = AnomalyPredictor(data_registry=mock_data_registry)
        assert model.name == "anomaly_predictor"
        assert model.algorithm_name == "random_forest"
        assert model.is_trained is False

    def test_init_custom(self, mock_data_registry):
        model = AnomalyPredictor(
            name="custom",
            algorithm_name="xgboost",
            data_registry=mock_data_registry,
            device_id="dev-1",
        )
        assert model.name == "custom"
        assert model.algorithm_name == "xgboost"
        assert model.device_id == "dev-1"


class TestAnomalyPredictorBuildFeatureColumns:
    def test_build_feature_columns(self, mock_data_registry):
        model = AnomalyPredictor(data_registry=mock_data_registry)
        cols = model._build_feature_columns(
            telemetry_keys=["volt", "rotate"],
            error_keys=["error1", "error2"],
            component_keys=["comp1", "comp2"],
        )
        assert "voltmean_3h" in cols
        assert "rotatesd_24h" in cols
        assert "error1count" in cols
        assert "error2count" in cols
        assert "comp1" in cols
        assert "age" in cols
        assert len(cols) == 13


class TestCreateErrorCountFeatures:
    def test_empty_errors(self, sample_telemetry):
        errors = pd.DataFrame({"datetime": [], "errorID": [], "machineID": []})
        error_classes = ["error1", "error2", "error3", "error4", "error5"]
        result = create_error_count_features(sample_telemetry, errors, error_classes)
        assert not result.empty
        for ec in error_classes:
            assert f"{ec}count" in result.columns

    def test_with_errors(self, sample_telemetry, sample_errors):
        error_classes = ["error1", "error2", "error3", "error4", "error5"]
        result = create_error_count_features(sample_telemetry, sample_errors, error_classes)
        assert not result.empty
        assert "datetime" in result.columns
        for ec in error_classes:
            assert f"{ec}count" in result.columns


class TestCreateTelemetryFeatures:
    def test_creates_features(self, sample_telemetry):
        result = create_telemetry_features(sample_telemetry)
        assert not result.empty
        assert "voltmean_3h" in result.columns
        assert "voltmean_24h" in result.columns
        assert "voltsd_3h" in result.columns
        assert "voltsd_24h" in result.columns


class TestCreateTargets:
    def test_creates_target_columns(self, anomaly_training_df):
        labeled = anomaly_training_df.copy()
        labeled["machineID"] = 1
        labeled["datetime"] = pd.date_range("2015-01-01", periods=len(labeled), freq="3h")
        labeled["failure"] = labeled["failure_component"]
        result = create_targets(labeled)
        for hour in [1, 4, 8, 12, 16, 20, 24]:
            assert f"target_hour_{hour}_multiclass" in result.columns
            assert f"target_hour_{hour}_binary" in result.columns


class TestCreateAndTrainHourlyModels:
    def test_train_random_forest(self, anomaly_training_df):
        df = anomaly_training_df.copy()
        df["machineID"] = 1
        df["datetime"] = pd.date_range("2015-01-01", periods=len(df), freq="3h")
        df["failure"] = df["failure_component"]
        df = create_targets(df)
        feature_cols = [c for c in df.columns if c not in [
            "datetime", "failure", "failure_component",
        ] + [f"target_hour_{h}_multiclass" for h in range(1, 25)]
        + [f"target_hour_{h}_binary" for h in range(1, 25)]]
        train = df.iloc[:200]
        X_train = train[feature_cols]
        models = create_and_train_hourly_models(
            train, train, train, X_train, X_train, X_train,
            feature_cols, ["comp1", "comp2", "comp3", "comp4"], algorithm="random_forest"
        )
        assert len(models) > 0
        for key in models:
            assert key.startswith("hour_")

    def test_train_xgboost(self, anomaly_training_df):
        df = anomaly_training_df.copy()
        df["machineID"] = 1
        df["datetime"] = pd.date_range("2015-01-01", periods=len(df), freq="3h")
        df["failure"] = df["failure_component"]
        df = create_targets(df)
        feature_cols = [c for c in df.columns if c not in [
            "datetime", "failure", "failure_component",
        ] + [f"target_hour_{h}_multiclass" for h in range(1, 25)]
        + [f"target_hour_{h}_binary" for h in range(1, 25)]]
        train = df.iloc[:200]
        X_train = train[feature_cols]
        models = create_and_train_hourly_models(
            train, train, train, X_train, X_train, X_train,
            feature_cols, ["comp1", "comp2", "comp3", "comp4"], algorithm="xgboost"
        )
        assert len(models) > 0

    def test_unknown_algorithm_falls_back_to_rf(self, anomaly_training_df):
        df = anomaly_training_df.copy()
        df["machineID"] = 1
        df["datetime"] = pd.date_range("2015-01-01", periods=len(df), freq="3h")
        df["failure"] = df["failure_component"]
        df = create_targets(df)
        feature_cols = [c for c in df.columns if c not in [
            "datetime", "failure", "failure_component",
        ] + [f"target_hour_{h}_multiclass" for h in range(1, 25)]
        + [f"target_hour_{h}_binary" for h in range(1, 25)]]
        train = df.iloc[:200]
        X_train = train[feature_cols]
        models = create_and_train_hourly_models(
            train, train, train, X_train, X_train, X_train,
            feature_cols, ["comp1", "comp2", "comp3", "comp4"], algorithm="unknown_algo"
        )
        assert len(models) > 0


class TestPredictNext24hHourlyFailures:
    def test_prediction_structure(self, anomaly_training_df, hourly_models_dict):
        df = anomaly_training_df.copy()
        df["machineID"] = 1
        df["datetime"] = pd.date_range("2015-01-01", periods=len(df), freq="3h")
        feature_cols = [c for c in df.columns if c not in ["datetime", "failure_component"]]
        result = predict_next_24h_hourly_failures(
            telemetry_data={"volt": 150, "rotate": 400, "pressure": 90, "vibration": 50},
            labeled_features_clean=df,
            feature_cols_in=feature_cols,
            hourly_models=hourly_models_dict,
        )
        assert "prediction_start_datetime" in result
        assert "hourly_predictions" in result
        assert len(result["hourly_predictions"]) == 24
        for hour in range(1, 25):
            key = f"hour_{hour}"
            assert key in result["hourly_predictions"]
            hp = result["hourly_predictions"][key]
            assert "general_failure_probability" in hp
            assert "predicted_failing_component" in hp
            assert "component_probabilities" in hp

    def test_empty_features_raises(self, hourly_models_dict):
        df = pd.DataFrame()
        with pytest.raises(ValueError, match="empty"):
            predict_next_24h_hourly_failures({}, df, [], hourly_models_dict)


class TestSaveAndLoadModels:
    def test_save_and_load(self, hourly_models_dict, tmp_path):
        save_models(hourly_models_dict, tmp_path)
        loaded = load_models(tmp_path)
        assert len(loaded) == len(hourly_models_dict)
        for key in hourly_models_dict:
            assert key in loaded

    def test_load_nonexistent_returns_empty(self, tmp_path):
        loaded = load_models(tmp_path / "nonexistent")
        assert loaded == {}
