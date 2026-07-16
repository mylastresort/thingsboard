import pytest

from library.algorithms.factory import AlgorithmRegistry
from library.algorithms.supervised.random_forest import RandomForestAdapter
from library.algorithms.supervised.xgboost_adapter import XGBoostAdapter
from library.algorithms.timeseries.xgboost_ts import XGBoostTimeSeriesAdapter
from library.core.types import (
    AlgorithmConfig,
    AlgorithmType,
    SupervisedConfig,
    TaskType,
    TimeSeriesConfig,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    original = AlgorithmRegistry._algorithms.copy()
    yield
    AlgorithmRegistry._algorithms = original


class TestAlgorithmRegistry:
    def test_algorithms_registered(self):
        assert AlgorithmRegistry.is_registered("random_forest")
        assert AlgorithmRegistry.is_registered("xgboost")
        assert AlgorithmRegistry.is_registered("xgboost_ts")

    def test_list_algorithms(self):
        algos = AlgorithmRegistry.list_algorithms()
        assert "random_forest" in algos
        assert "xgboost" in algos
        assert "xgboost_ts" in algos

    def test_create_random_forest(self):
        config = SupervisedConfig(
            name="random_forest",
            algorithm_type=AlgorithmType.SUPERVISED,
            task_type=TaskType.BINARY_CLASSIFICATION,
        )
        algo = AlgorithmRegistry.create(config)
        assert isinstance(algo, RandomForestAdapter)

    def test_create_xgboost(self):
        config = SupervisedConfig(
            name="xgboost",
            algorithm_type=AlgorithmType.SUPERVISED,
            task_type=TaskType.BINARY_CLASSIFICATION,
        )
        algo = AlgorithmRegistry.create(config)
        assert isinstance(algo, XGBoostAdapter)

    def test_create_xgboost_ts(self):
        config = TimeSeriesConfig(name="xgboost_ts", algorithm_type="time_series", task_type="time_series_forecast")
        algo = AlgorithmRegistry.create(config)
        assert isinstance(algo, XGBoostTimeSeriesAdapter)

    def test_create_unknown_raises(self):
        config = AlgorithmConfig(
            name="nonexistent",
            algorithm_type=AlgorithmType.SUPERVISED,
            task_type=TaskType.REGRESSION,
        )
        with pytest.raises(ValueError, match="not found"):
            AlgorithmRegistry.create(config)

    def test_register_custom_algorithm(self):
        class CustomAlgo:
            pass

        AlgorithmRegistry.register("custom_test", CustomAlgo)
        assert AlgorithmRegistry.is_registered("custom_test")
        assert "custom_test" in AlgorithmRegistry.list_algorithms()

    def test_is_registered_false(self):
        assert not AlgorithmRegistry.is_registered("does_not_exist")
