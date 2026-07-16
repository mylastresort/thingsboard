import numpy as np
import pandas as pd
import pytest

from library.models.forecast_model import (
    create_rnn_dataset,
    prepare_sensor_data,
    scale_and_split_data,
    generate_date_range,
    ForecastModel,
)


class TestPrepareSensorData:
    def test_basic(self):
        df = pd.DataFrame({"datetime": pd.date_range("2024-01-01", periods=100, freq="h"), "sensor_00": np.random.rand(100)})
        result = prepare_sensor_data(df, "sensor_00")
        assert "sensor_00" in result.columns
        assert len(result) == 100
        assert result["sensor_00"].dtype == int

    def test_missing_sensor_raises(self):
        df = pd.DataFrame({"datetime": pd.date_range("2024-01-01", periods=10, freq="h"), "other": range(10)})
        with pytest.raises(ValueError, match="not found"):
            prepare_sensor_data(df, "sensor_00")

    def test_forward_fills_nans(self):
        vals = [1.0, np.nan, np.nan, 4.0, 5.0]
        df = pd.DataFrame({"datetime": pd.date_range("2024-01-01", periods=5, freq="h"), "sensor_00": vals})
        result = prepare_sensor_data(df, "sensor_00")
        assert result["sensor_00"].isnull().sum() == 0
        assert result["sensor_00"].iloc[1] == 1.0
        assert result["sensor_00"].iloc[2] == 1.0


class TestScaleAndSplitData:
    def test_shapes(self):
        data = pd.DataFrame({"sensor_00": np.random.rand(200)})
        train, test, scaler = scale_and_split_data(data, "sensor_00", 0.8, 10)
        assert len(train) > 0
        assert len(test) > 0
        assert scaler is not None

    def test_overlap_by_lookback(self):
        data = pd.DataFrame({"sensor_00": np.arange(100, dtype=float)})
        train, test, scaler = scale_and_split_data(data, "sensor_00", 0.7, 10)
        train_size = int(0.7 * 100)
        expected_test_len = 100 - train_size + 10
        assert len(test) == expected_test_len


class TestCreateRnnDataset:
    def test_shapes(self):
        data = np.arange(100, dtype=float).reshape(-1, 1)
        X, y = create_rnn_dataset(data, lookback=10)
        assert X.shape == (89, 10)
        assert y.shape == (89,)

    def test_lookback_1(self):
        data = np.arange(20, dtype=float).reshape(-1, 1)
        X, y = create_rnn_dataset(data, lookback=1)
        assert X.shape == (18, 1)
        assert y.shape == (18,)

    def test_values(self):
        data = np.arange(10, dtype=float).reshape(-1, 1)
        X, y = create_rnn_dataset(data, lookback=3)
        np.testing.assert_array_equal(X[0], data[:3, 0])
        assert y[0] == data[3, 0]


class TestGenerateDateRange:
    def test_basic(self):
        from datetime import datetime
        result = generate_date_range(datetime(2024, 1, 1, 0, 0), 3)
        assert len(result) == 3
        assert result[0] == "2024-01-01 00:00"
        assert result[1] == "2024-01-01 01:00"
        assert result[2] == "2024-01-01 02:00"

    def test_zero_hours(self):
        from datetime import datetime
        result = generate_date_range(datetime(2024, 1, 1), 0)
        assert result == []


class TestForecastModelInit:
    def test_defaults(self):
        model = ForecastModel()
        assert model.name == "forecast_model"
        assert model.lookback == 20
        assert model.is_trained is False

    def test_custom_params(self):
        model = ForecastModel(
            sensors=["s1", "s2"],
            name="custom",
            lookback=50,
            device_id="dev-1",
        )
        assert model.sensors == ["s1", "s2"]
        assert model.name == "custom"
        assert model.lookback == 50
        assert model.device_id == "dev-1"


class TestForecastModelGenerateSampleData:
    def test_generates_data(self):
        model = ForecastModel()
        df = model._generate_sample_data(sensor_key="test_sensor", n_days=5)
        assert len(df) == 5 * 24
        assert "datetime" in df.columns
        assert "test_sensor" in df.columns
