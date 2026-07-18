import numpy as np
import pandas as pd
import pytest

from library.algorithms.timeseries.xgboost_ts import XGBoostTimeSeriesAdapter
from library.core.types import (
    AlgorithmCapabilities,
    ForecastOutput,
    PredictionOutput,
    TimeSeriesConfig,
    TrainingMetrics,
)


@pytest.fixture
def ts_config():
    return TimeSeriesConfig(
        name="xgboost_ts",
        algorithm_type="time_series",
        task_type="time_series_forecast",
        time_column="timestamp",
        value_column="value",
        forecast_horizon=24,
        hyperparameters={"n_lags": 12, "test_size": 0.2},
        random_state=42,
    )


class TestXGBoostTimeSeriesCapabilities:
    def test_capabilities(self):
        config = TimeSeriesConfig(name="xgboost_ts", algorithm_type="time_series", task_type="time_series_forecast")
        algo = XGBoostTimeSeriesAdapter(config)
        caps = algo.capabilities
        assert caps.supports_classification is False
        assert caps.supports_regression is False
        assert caps.supports_time_series is True
        assert caps.supports_feature_importance is True
        assert caps.supports_probability is False
        assert caps.supports_incremental_learning is True


class TestXGBoostTimeSeriesLaggedFeatures:
    def test_create_lagged_features(self, ts_config, time_series_data):
        algo = XGBoostTimeSeriesAdapter(ts_config)
        df = algo._create_lagged_features(time_series_data, n_lags=12)
        assert "lag_1" in df.columns
        assert "lag_12" in df.columns
        assert "rolling_mean_6" in df.columns
        assert "rolling_std_24" in df.columns
        assert "hour" in df.columns
        assert "day_of_week" in df.columns
        assert "day_of_month" in df.columns
        assert "month" in df.columns
        assert len(df) < len(time_series_data)
        assert df.isnull().sum().sum() == 0


class TestXGBoostTimeSeriesTrain:
    def test_train(self, ts_config, time_series_data):
        algo = XGBoostTimeSeriesAdapter(ts_config)
        metrics = algo.train(time_series_data)
        assert algo.is_trained is True
        assert isinstance(metrics, TrainingMetrics)
        assert metrics.rmse is not None
        assert metrics.rmse >= 0
        assert metrics.mae is not None
        assert metrics.mae >= 0
        assert metrics.r2_score is not None
        assert metrics.feature_importances is not None
        assert algo.last_values is not None
        assert algo.last_timestamp is not None

    def test_train_stores_last_values(self, ts_config, time_series_data):
        algo = XGBoostTimeSeriesAdapter(ts_config)
        algo.train(time_series_data)
        assert len(algo.last_values) == 12


class TestXGBoostTimeSeriesPredict:
    def test_predict(self, ts_config, time_series_data):
        algo = XGBoostTimeSeriesAdapter(ts_config)
        algo.train(time_series_data)
        output = algo.predict(time_series_data)
        assert isinstance(output, PredictionOutput)
        assert len(output.predictions) > 0
        assert output.metadata["algorithm"] == "xgboost_ts"

    def test_predict_untrained_raises(self, ts_config, time_series_data):
        algo = XGBoostTimeSeriesAdapter(ts_config)
        with pytest.raises(ValueError, match="must be trained"):
            algo.predict(time_series_data)


class TestXGBoostTimeSeriesForecast:
    def test_forecast(self, ts_config, time_series_data):
        algo = XGBoostTimeSeriesAdapter(ts_config)
        algo.train(time_series_data)
        output = algo.forecast(periods=12, freq="H")
        assert isinstance(output, ForecastOutput)
        assert len(output.forecasted_values) == 12
        assert len(output.timestamps) == 12
        assert output.metadata["algorithm"] == "xgboost_ts"
        assert output.metadata["periods"] == 12

    def test_forecast_daily_freq(self, ts_config, time_series_data):
        algo = XGBoostTimeSeriesAdapter(ts_config)
        algo.train(time_series_data)
        output = algo.forecast(periods=5, freq="D")
        assert len(output.forecasted_values) == 5

    def test_forecast_untrained_raises(self, ts_config):
        algo = XGBoostTimeSeriesAdapter(ts_config)
        with pytest.raises(ValueError, match="must be trained"):
            algo.forecast(10)

    def test_forecast_output_timestamps_are_sequential(self, ts_config, time_series_data):
        algo = XGBoostTimeSeriesAdapter(ts_config)
        algo.train(time_series_data)
        output = algo.forecast(periods=6, freq="H")
        for i in range(1, len(output.timestamps)):
            diff = output.timestamps[i] - output.timestamps[i - 1]
            assert diff.total_seconds() == 3600


class TestXGBoostTimeSeriesFeatureImportance:
    def test_get_feature_importance(self, ts_config, time_series_data):
        algo = XGBoostTimeSeriesAdapter(ts_config)
        algo.train(time_series_data)
        importance = algo.get_feature_importance()
        assert importance is not None
        assert isinstance(importance, dict)

    def test_get_feature_importance_untrained(self, ts_config):
        algo = XGBoostTimeSeriesAdapter(ts_config)
        assert algo.get_feature_importance() is None
