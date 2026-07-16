import numpy as np
import pytest
from datetime import datetime

from library.core.types import (
    AlgorithmCapabilities,
    AlgorithmConfig,
    AlgorithmType,
    ForecastOutput,
    NeuralNetworkConfig,
    PredictionOutput,
    SupervisedConfig,
    TaskType,
    TimeSeriesConfig,
    TrainingMetrics,
)


class TestAlgorithmType:
    def test_enum_values(self):
        assert AlgorithmType.SUPERVISED.value == "supervised"
        assert AlgorithmType.TIME_SERIES.value == "time_series"
        assert AlgorithmType.NEURAL_NETWORK.value == "neural_network"

    def test_str_enum(self):
        assert isinstance(AlgorithmType.SUPERVISED, str)
        assert AlgorithmType.SUPERVISED == "supervised"


class TestTaskType:
    def test_enum_values(self):
        assert TaskType.BINARY_CLASSIFICATION.value == "binary_classification"
        assert TaskType.MULTICLASS_CLASSIFICATION.value == "multiclass_classification"
        assert TaskType.REGRESSION.value == "regression"
        assert TaskType.TIME_SERIES_FORECAST.value == "time_series_forecast"
        assert TaskType.ANOMALY_DETECTION.value == "anomaly_detection"


class TestAlgorithmConfig:
    def test_defaults(self):
        config = AlgorithmConfig(
            name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION
        )
        assert config.random_state == 42
        assert config.hyperparameters == {}

    def test_to_dict(self):
        config = AlgorithmConfig(
            name="rf",
            algorithm_type=AlgorithmType.SUPERVISED,
            task_type=TaskType.BINARY_CLASSIFICATION,
            hyperparameters={"n_estimators": 100},
        )
        d = config.to_dict()
        assert d["name"] == "rf"
        assert d["algorithm_type"] == "supervised"
        assert d["task_type"] == "binary_classification"
        assert d["hyperparameters"] == {"n_estimators": 100}


class TestSupervisedConfig:
    def test_defaults(self):
        config = SupervisedConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION)
        assert config.test_size == 0.2
        assert config.cv_folds == 5
        assert config.feature_columns == []

    def test_post_init_fixes_algorithm_type(self):
        config = SupervisedConfig(name="test", algorithm_type=AlgorithmType.TIME_SERIES, task_type=TaskType.REGRESSION)
        assert config.algorithm_type == AlgorithmType.SUPERVISED

    def test_allows_neural_network_type(self):
        config = SupervisedConfig(name="test", algorithm_type=AlgorithmType.NEURAL_NETWORK, task_type=TaskType.REGRESSION)
        assert config.algorithm_type == AlgorithmType.NEURAL_NETWORK


class TestTimeSeriesConfig:
    def test_post_init_overrides(self):
        config = TimeSeriesConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION)
        assert config.algorithm_type == AlgorithmType.TIME_SERIES
        assert config.task_type == TaskType.TIME_SERIES_FORECAST

    def test_defaults(self):
        config = TimeSeriesConfig(name="test", algorithm_type=AlgorithmType.TIME_SERIES, task_type=TaskType.TIME_SERIES_FORECAST)
        assert config.forecast_horizon == 24
        assert config.time_column == "timestamp"
        assert config.value_column == "value"


class TestNeuralNetworkConfig:
    def test_post_init(self):
        config = NeuralNetworkConfig(name="test", algorithm_type=AlgorithmType.NEURAL_NETWORK, task_type=TaskType.REGRESSION)
        assert config.algorithm_type == AlgorithmType.NEURAL_NETWORK

    def test_defaults(self):
        config = NeuralNetworkConfig(name="test", algorithm_type=AlgorithmType.NEURAL_NETWORK, task_type=TaskType.REGRESSION)
        assert config.hidden_layers == [64, 32]
        assert config.epochs == 100
        assert config.learning_rate == 0.001


class TestPredictionOutput:
    def test_to_dict(self):
        out = PredictionOutput(predictions=np.array([1, 0, 1]), probabilities=np.array([[0.2, 0.8], [0.9, 0.1], [0.3, 0.7]]))
        d = out.to_dict()
        assert d["predictions"] == [1, 0, 1]
        assert len(d["probabilities"]) == 3
        assert "prediction_time" in d

    def test_to_dict_no_probabilities(self):
        out = PredictionOutput(predictions=np.array([1, 0]))
        d = out.to_dict()
        assert d["probabilities"] is None

    def test_metadata(self):
        out = PredictionOutput(predictions=np.array([1]), metadata={"algo": "rf"})
        assert out.metadata["algo"] == "rf"


class TestTrainingMetrics:
    def test_defaults(self):
        m = TrainingMetrics()
        assert m.accuracy is None
        assert m.training_time == 0.0

    def test_to_dict(self):
        m = TrainingMetrics(accuracy=0.95, f1_score=0.9, confusion_matrix=np.array([[10, 2], [1, 12]]))
        d = m.to_dict()
        assert d["accuracy"] == 0.95
        assert d["f1_score"] == 0.9
        assert d["confusion_matrix"] == [[10, 2], [1, 12]]

    def test_to_dict_no_confusion_matrix(self):
        m = TrainingMetrics(accuracy=0.8)
        d = m.to_dict()
        assert d["confusion_matrix"] is None


class TestForecastOutput:
    def test_to_dict(self):
        ts = [datetime(2024, 1, 1, i) for i in range(3)]
        out = ForecastOutput(timestamps=ts, forecasted_values=np.array([1.0, 2.0, 3.0]))
        d = out.to_dict()
        assert len(d["timestamps"]) == 3
        assert d["forecasted_values"] == [1.0, 2.0, 3.0]
        assert d["lower_bound"] is None

    def test_to_dict_with_bounds(self):
        ts = [datetime(2024, 1, 1)]
        out = ForecastOutput(
            timestamps=ts,
            forecasted_values=np.array([1.0]),
            lower_bound=np.array([0.5]),
            upper_bound=np.array([1.5]),
        )
        d = out.to_dict()
        assert d["lower_bound"] == [0.5]
        assert d["upper_bound"] == [1.5]


class TestAlgorithmCapabilities:
    def test_defaults(self):
        caps = AlgorithmCapabilities()
        assert caps.supports_classification is False
        assert caps.supports_time_series is False
        assert caps.requires_scaling is True

    def test_to_dict(self):
        caps = AlgorithmCapabilities(supports_classification=True, supports_feature_importance=True)
        d = caps.to_dict()
        assert d["supports_classification"] is True
        assert d["supports_feature_importance"] is True
        assert d["supports_time_series"] is False
