import numpy as np
import pandas as pd
import pytest

from library.algorithms.supervised.random_forest import RandomForestAdapter
from library.core.types import (
    AlgorithmCapabilities,
    PredictionOutput,
    SupervisedConfig,
    TaskType,
    TrainingMetrics,
)


@pytest.fixture
def binary_config():
    return SupervisedConfig(
        name="random_forest",
        algorithm_type="supervised",
        task_type=TaskType.BINARY_CLASSIFICATION,
        test_size=0.2,
        cv_folds=3,
        random_state=42,
    )


@pytest.fixture
def regression_config():
    return SupervisedConfig(
        name="random_forest",
        algorithm_type="supervised",
        task_type=TaskType.REGRESSION,
        test_size=0.2,
        cv_folds=3,
        random_state=42,
    )


class TestRandomForestCapabilities:
    def test_capabilities(self):
        config = SupervisedConfig(name="random_forest", algorithm_type="supervised", task_type=TaskType.REGRESSION)
        algo = RandomForestAdapter(config)
        caps = algo.capabilities
        assert caps.supports_classification is True
        assert caps.supports_regression is True
        assert caps.supports_time_series is False
        assert caps.supports_feature_importance is True
        assert caps.supports_probability is True
        assert caps.supports_incremental_learning is False
        assert caps.requires_scaling is False


class TestRandomForestBinaryClassification:
    def test_train(self, binary_config, classification_data):
        X, y = classification_data
        algo = RandomForestAdapter(binary_config)
        metrics = algo.train(X, y)
        assert algo.is_trained is True
        assert isinstance(metrics, TrainingMetrics)
        assert metrics.accuracy is not None
        assert 0.0 <= metrics.accuracy <= 1.0
        assert metrics.precision is not None
        assert metrics.recall is not None
        assert metrics.f1_score is not None
        assert metrics.roc_auc is not None
        assert 0.0 <= metrics.roc_auc <= 1.0
        assert metrics.confusion_matrix is not None
        assert metrics.cross_val_scores is not None
        assert len(metrics.cross_val_scores) == 3
        assert metrics.feature_importances is not None
        assert len(metrics.feature_importances) == X.shape[1]

    def test_predict(self, binary_config, classification_data):
        X, y = classification_data
        algo = RandomForestAdapter(binary_config)
        algo.train(X, y)
        output = algo.predict(X)
        assert isinstance(output, PredictionOutput)
        assert len(output.predictions) == len(X)
        assert output.probabilities is not None
        assert output.probabilities.shape == (len(X), 2)
        assert output.metadata["algorithm"] == "random_forest"
        assert output.metadata["n_samples"] == len(X)

    def test_predict_untrained_raises(self, binary_config):
        algo = RandomForestAdapter(binary_config)
        with pytest.raises(ValueError, match="must be trained"):
            algo.predict(pd.DataFrame({"a": [1]}))

    def test_train_requires_y(self, binary_config, classification_data):
        X, _ = classification_data
        algo = RandomForestAdapter(binary_config)
        with pytest.raises(ValueError, match="requires target"):
            algo.train(X, y=None)

    def test_get_feature_importance(self, binary_config, classification_data):
        X, y = classification_data
        algo = RandomForestAdapter(binary_config)
        algo.train(X, y)
        importance = algo.get_feature_importance()
        assert importance is not None
        assert isinstance(importance, dict)
        assert len(importance) == X.shape[1]

    def test_get_feature_importance_untrained(self, binary_config):
        algo = RandomForestAdapter(binary_config)
        assert algo.get_feature_importance() is None


class TestRandomForestMulticlassClassification:
    def test_train_multiclass(self, binary_config, multiclass_data):
        X, y = multiclass_data
        algo = RandomForestAdapter(binary_config)
        metrics = algo.train(X, y)
        assert algo.is_trained is True
        assert metrics.accuracy > 0
        assert metrics.roc_auc is None

    def test_predict_multiclass(self, binary_config, multiclass_data):
        X, y = multiclass_data
        algo = RandomForestAdapter(binary_config)
        algo.train(X, y)
        output = algo.predict(X)
        assert output.probabilities.shape[1] == 4


class TestRandomForestRegression:
    def test_train_regression(self, regression_config, regression_data):
        X, y = regression_data
        algo = RandomForestAdapter(regression_config)
        metrics = algo.train(X, y)
        assert algo.is_trained is True
        assert metrics.rmse is not None
        assert metrics.rmse >= 0
        assert metrics.mae is not None
        assert metrics.mae >= 0
        assert metrics.r2_score is not None
        assert metrics.accuracy is None

    def test_predict_regression(self, regression_config, regression_data):
        X, y = regression_data
        algo = RandomForestAdapter(regression_config)
        algo.train(X, y)
        output = algo.predict(X)
        assert len(output.predictions) == len(X)
