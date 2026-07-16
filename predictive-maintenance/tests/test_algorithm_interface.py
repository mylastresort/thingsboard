from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from library.core.algorithm_interface import BaseAlgorithm
from library.core.types import (
    AlgorithmCapabilities,
    AlgorithmConfig,
    AlgorithmType,
    PredictionOutput,
    TaskType,
    TrainingMetrics,
)


class ConcreteAlgorithm(BaseAlgorithm):
    def _define_capabilities(self):
        return AlgorithmCapabilities(supports_classification=True, supports_feature_importance=True)

    def train(self, X, y=None):
        self.is_trained = True
        self.training_metrics = TrainingMetrics(accuracy=0.9)
        return self.training_metrics

    def predict(self, X):
        return PredictionOutput(predictions=pd.Series([0] * len(X)))


class TestBaseAlgorithm:
    def test_init(self):
        config = AlgorithmConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION)
        algo = ConcreteAlgorithm(config)
        assert algo.config.name == "test"
        assert algo.is_trained is False
        assert algo.model is None

    def test_train(self):
        config = AlgorithmConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION)
        algo = ConcreteAlgorithm(config)
        X = pd.DataFrame({"a": [1, 2, 3]})
        metrics = algo.train(X)
        assert algo.is_trained is True
        assert metrics.accuracy == 0.9

    def test_predict(self):
        config = AlgorithmConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION)
        algo = ConcreteAlgorithm(config)
        algo.is_trained = True
        X = pd.DataFrame({"a": [1, 2, 3]})
        output = algo.predict(X)
        assert len(output.predictions) == 3

    def test_forecast_not_supported(self):
        config = AlgorithmConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION)
        algo = ConcreteAlgorithm(config)
        algo.is_trained = True
        with pytest.raises(NotImplementedError, match="does not support"):
            algo.forecast(10)

    def test_get_feature_importance_when_supported(self):
        config = AlgorithmConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION)
        algo = ConcreteAlgorithm(config)
        algo.is_trained = True
        result = algo.get_feature_importance()
        assert result is None

    def test_save_untrained_raises(self, tmp_path):
        config = AlgorithmConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION)
        algo = ConcreteAlgorithm(config)
        with pytest.raises(ValueError, match="untrained"):
            algo.save(tmp_path / "model.pkl")

    def test_save_and_load(self, tmp_path):
        config = AlgorithmConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION)
        algo = ConcreteAlgorithm(config)
        algo.is_trained = True
        algo.model = "dummy_model"
        save_path = tmp_path / "model.pkl"
        algo.save(save_path)

        algo2 = ConcreteAlgorithm(config)
        algo2.load(save_path)
        assert algo2.is_trained is True
        assert algo2.model == "dummy_model"

    def test_capabilities_property(self):
        config = AlgorithmConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION)
        algo = ConcreteAlgorithm(config)
        assert algo.capabilities.supports_classification is True
        assert algo.capabilities.supports_feature_importance is True

    def test_algorithm_type_property(self):
        config = AlgorithmConfig(name="test", algorithm_type=AlgorithmType.TIME_SERIES, task_type=TaskType.TIME_SERIES_FORECAST)
        algo = ConcreteAlgorithm(config)
        assert algo.algorithm_type == AlgorithmType.TIME_SERIES

    def test_task_type_property(self):
        config = AlgorithmConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.MULTICLASS_CLASSIFICATION)
        algo = ConcreteAlgorithm(config)
        assert algo.task_type == TaskType.MULTICLASS_CLASSIFICATION

    def test_repr(self):
        config = AlgorithmConfig(name="test", algorithm_type=AlgorithmType.SUPERVISED, task_type=TaskType.REGRESSION)
        algo = ConcreteAlgorithm(config)
        assert "untrained" in repr(algo)
        algo.is_trained = True
        assert "trained" in repr(algo)
