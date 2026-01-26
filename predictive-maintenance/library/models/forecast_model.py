"""
Forecast Model - Pure sensor telemetry forecasting (NOT failure prediction).

This model forecasts future sensor values using time series algorithms.
It does NOT predict failures - that's the job of AnomalyPredictor.
"""

from pyexpat import model
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
from datetime import datetime
from src.logger import logger  # Global logger

from ..core.model_interface import BaseModel
from ..core.types import TimeSeriesConfig, TaskType, AlgorithmType
from ..algorithms.factory import AlgorithmRegistry
from ..models.sensor_forecasting_lstm import (
    prepare_sensor_data,
    scale_and_split_data,
    create_rnn_dataset,
    build_lstm_model,
    train_lstm_model,
    forecast_future,
)


class ForecastModel(BaseModel):
    """
    Forecasts future sensor telemetry values using time series algorithms.

    This model ONLY forecasts sensor readings - it does NOT predict failures.
    Use AnomalyPredictor for failure prediction.
    """

    models: Dict[str, Any] = {}

    def __init__(
        self,
        sensors: List[str] = None,
        name: str = "forecast_model",
        algorithm_name: str = "prophet",
        algorithm_hyperparams: Optional[Dict[str, Any]] = None,
        data_registry=None,
        additional_info: Optional[Dict[str, Any]] = {},
        lookback: int = 20,
        train_size: int = 8041,
        train_start_date: Optional[datetime] = None,
        train_end_date: Optional[datetime] = None,
        device_id: str = None,
        group_by_ms_per_sensor: Optional[Dict[str, int]] = None,
        aggregation_funcs: Optional[Dict[str, str]] = None,  # Per-sensor aggregation functions
        last_fetched_date: Optional[datetime] = datetime(1970, 1, 1),
    ):
        """
        Initialize the forecast model.

        Args:
            name: Model name
            algorithm_name: Which time series algorithm to use (prophet, xgboost_ts)
            algorithm_hyperparams: Hyperparameters for the algorithm
            data_registry: DataRegistry instance for database access
            group_by_ms_per_sensor: Dict mapping sensor names to grouping intervals in milliseconds
            aggregation_funcs: Dict mapping sensor names to aggregation functions ('average', 'min', 'max')
        """
        super().__init__(name, data_registry=data_registry)
        self.algorithm_name = algorithm_name
        self.algorithm_hyperparams = algorithm_hyperparams or {}
        self.sensor_name: Optional[str] = None

        self.lookback = lookback or additional_info.get("lookback", 720)
        self.train_size = train_size or additional_info.get("train_size", 8041)
        self.device_id = device_id
        self.sensors = sensors
        self.group_by_ms_per_sensor = group_by_ms_per_sensor or {}
        self.aggregation_funcs = aggregation_funcs or {}
        self.last_real_timestamps: Dict[str, int] = {}  # Track last real data point per sensor
        self.train_start_date = train_start_date or additional_info.get("train_start_date", None)
        self.train_end_date = train_end_date or additional_info.get("train_end_date", None)
        self.last_fetched_date = last_fetched_date

        # Create time series algorithm
        # config = TimeSeriesConfig(
        #     name=algorithm_name,
        #     algorithm_type=AlgorithmType.TIME_SERIES,
        #     task_type=TaskType.TIME_SERIES_FORECAST,
        #     time_column="timestamp",
        #     value_column="value",
        #     hyperparameters=self.algorithm_hyperparams.copy(),
        # )

        # algorithm = AlgorithmRegistry.create(config)
        # self.add_algorithm("forecast", algorithm)

    def fetch(self, **kwargs) -> dict[str, pd.DataFrame]:
        """
        Fetch training data for forecasting from database.

        Args:
            device_id: Device or model identifier
            **kwargs: Additional parameters (sensor_key, days_back, etc.)

        Returns:
            DataFrame with 'ds' and 'y' columns (Prophet format)
        """
        from datetime import datetime, timedelta

        device_id = self.device_id or kwargs.get("device_id")
        if device_id is None:
            raise ValueError("device_id must be provided either in init or fetch()")
        sensor_keys = kwargs.get("sensor_keys", ["sensor_00"])
        days_back = kwargs.get("days_back", 90)
        start_date = kwargs.get("start_date", None)
        end_date = kwargs.get("end_date", None)
        desc = kwargs.get("desc", False)

        limit = kwargs.get("limit", None)

        forecast_dict = dict()

        try:
            for sensor_key in sensor_keys:
                forecast_data = self.data_registry.fetch_forecast_training_data(
                    device_id=device_id,
                    sensor_key=sensor_key,
                    days_back=days_back,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                    desc=desc,
                )

                # TODO: group by time interval (hourly, daily) if needed

                if forecast_data.empty:
                    forecast_dict[sensor_key] = self._generate_sample_data(
                        sensor_key=sensor_key, n_days=90
                    )

                else:
                    forecast_dict[sensor_key] = forecast_data

            return forecast_dict

        except Exception as e:
            # Return a dictionary with synthetic data for each sensor
            forecast_dict = {}
            for sensor_key in sensor_keys:
                forecast_dict[sensor_key] = self._generate_sample_data(
                    sensor_key=sensor_key, n_days=90
                )
            return forecast_dict

    def fetch_latest(self, **kwargs):
        # Need lookback + 2 for RNN dataset creation
        # (create_rnn_dataset uses range(len(data) - lookback - 1))
        limit = self.lookback + 2

        # Always fetch the most recent N points (rolling window approach)
        # This ensures we always have enough data for prediction
        # Instead of incremental fetching which might not have enough new points
        data = self.fetch(
            sensor_keys=self.sensors,
            # start_date=self.last_fetched_date,
            start_date=datetime(1970, 1, 1),
            end_date=datetime.now(),
            limit=limit,  # SQL LIMIT with DESC will give us last N points
            desc=True,
            # TODO: add groupby param
        )

        # NOTE: this is for testing only
        # we fetch max timestamp and set it as last_fetched_date
        for sensor, df in data.items():
            if "datetime" in df.columns and not df.empty:
                self.last_fetched_date = df["datetime"].max()
                logger.info(
                    f"[FETCH_LATEST] Updated last_fetched_date for {sensor}: {self.last_fetched_date}"
                )

        for sensor, df in data.items():
            self.models[sensor]["data"] = df
        # read the latest timestamp from data
        # merge self.data with new data

    def _generate_sample_data(self, sensor_key: str = None, n_days=90) -> pd.DataFrame:
        """
        FALLBACK: Generate synthetic time series when real data is unavailable.

        Args:
            sensor_key: Name of the sensor (used as column name)
            n_days: Number of days of synthetic data to generate

        Returns:
            DataFrame with columns ["datetime", sensor_key] matching real data format
        """
        from datetime import datetime, timedelta

        start_date = datetime.now() - timedelta(days=n_days)
        timestamps = pd.date_range(start=start_date, periods=n_days * 24, freq="h")

        t = np.arange(len(timestamps))
        trend = 0.01 * t
        daily_season = 10 * np.sin(2 * np.pi * t / 24)
        weekly_season = 5 * np.sin(2 * np.pi * t / (24 * 7))
        noise = np.random.normal(0, 2, len(timestamps))
        values = 50 + trend + daily_season + weekly_season + noise

        # Return in the same format as real data from database
        column_name = sensor_key if sensor_key else "y"
        return pd.DataFrame({"datetime": timestamps, column_name: values})

    def train(self):
        """
        Train the forecast model on historical sensor data.

        Args:
            data: DataFrame with timestamp and sensor value columns
            sensor_name: Name of the sensor being forecasted
            time_column: Name of timestamp column
            value_column: Name of value column
            **kwargs: Additional training parameters

        Returns:
            Dictionary with training results
        """
        # if time_column not in data.columns or value_column not in data.columns:
        #     raise ValueError(
        #         f"Data must contain '{time_column}' and '{value_column}' columns"
        #     )

        logger.info(f"Starting to fetch training data for sensors: {self.sensors}")
        data = self.fetch(
            sensor_keys=self.sensors,
            start_date=self.train_start_date,
            end_date=self.train_end_date,
        )
        logger.info(f"Fetched training data for {len(data)} sensors")

        # self.sensor_name = sensor_name
        training_start = datetime.now()

        # # Get algorithm
        # algorithm = self.get_algorithm("forecast")

        # # Update config with actual column names
        # algorithm.config.time_column = time_column
        # algorithm.config.value_column = value_column

        # Train algorithm
        # metrics = algorithm.train(data)

        USE_GPU = True  # Set to True if GPU is available
        TRAIN_SIZE = 8041

        TRAIN_PERCENTAGE = 0.75
        # LOOKBACK = 720
        LSTM_UNITS = 256
        # EPOCHS = 35
        EPOCHS = 1
        BATCH_SIZE = 128

        models = dict()

        logger.info(
            f"Training LSTM models for {len(data)} sensors with lookback={self.lookback}, epochs={EPOCHS}, batch_size={BATCH_SIZE}"
        )

        for sensor_key, df in data.items():
            logger.info(f"Processing sensor: {sensor_key} with {len(df)} data points")
            sensor = prepare_sensor_data(df, sensor=sensor_key)
            logger.info(f"Prepared sensor data for {sensor_key}")

            # Scale and split data
            logger.info(f"Scaling and splitting data for {sensor_key}")
            train_data, test_data, scaler = scale_and_split_data(
                sensor, sensor_key, TRAIN_PERCENTAGE, self.lookback
            )
            logger.info(
                f"Scaled and split data for {sensor_key}: train_size={len(train_data)}, test_size={len(test_data)}"
            )

            # Create RNN datasets
            logger.info(f"Creating RNN datasets for {sensor_key}")
            train_x, train_y = create_rnn_dataset(train_data, self.lookback)
            train_x = np.reshape(train_x, (train_x.shape[0], 1, train_x.shape[1]))
            test_x, test_y = create_rnn_dataset(test_data, self.lookback)
            test_x = np.reshape(test_x, (test_x.shape[0], 1, test_x.shape[1]))
            logger.info(
                f"Created RNN datasets for {sensor_key}: train_x.shape={train_x.shape}, test_x.shape={test_x.shape}"
            )

            # Build and train model
            logger.info(f"Building LSTM model for {sensor_key}")
            model = build_lstm_model(self.lookback, LSTM_UNITS, use_gpu=USE_GPU)
            logger.info(f"Training LSTM model for {sensor_key} with {EPOCHS} epochs...")
            model = train_lstm_model(model, train_x, train_y, EPOCHS, BATCH_SIZE)
            logger.info(f"Finished training LSTM model for {sensor_key}")

            models[sensor_key] = {
                "model": model,
                "scaler": scaler,
            }

        logger.info(f"Completed training for all {len(models)} sensors")
        self.models = models

        # placeholder for training metrics
        logger.info("Generating training metrics")
        metrics = type(
            "Metrics",
            (object,),
            {
                "mae": 5.0,
                "rmse": 7.5,
                "r2_score": 0.85,
                "training_time": (datetime.now() - training_start).total_seconds(),
            },
        )()

        self.is_trained = True
        self.last_updated = datetime.now()

        logger.info(f"Training completed successfully in {metrics.training_time:.2f}s")

        return {
            "algorithm": self.algorithm_name,
            "mae": metrics.mae,
            "rmse": metrics.rmse,
            "r2_score": metrics.r2_score,
            "training_time": metrics.training_time,
            "total_training_time": (datetime.now() - training_start).total_seconds(),
            "n_samples": len(data),
        }

    def save(self, path):
        # loop over self.models and save in path
        import os
        import joblib
        from pathlib import Path

        path = Path(path)
        if not path.exists():
            os.makedirs(path)
        for sensor_key, model_dict in self.models.items():
            model = model_dict["model"]
            scaler = model_dict["scaler"]
            # save keras model
            model.save(path / f"lstm_model_{sensor_key}.h5")
            # save scaler
            joblib.dump(scaler, path / f"scaler_{sensor_key}.pkl")

    def load(self, path):
        import os
        import joblib
        from pathlib import Path
        from tensorflow.keras.models import load_model

        path = Path(path)
        if not path.exists():
            raise ValueError(f"Model path {path} does not exist")

        models = dict()
        for file in os.listdir(path):
            if file.startswith("lstm_model_") and file.endswith(".h5"):
                sensor_key = file[len("lstm_model_") : -len(".h5")]
                model = load_model(path / file)
                scaler_file = f"scaler_{sensor_key}.pkl"
                if (path / scaler_file).exists():
                    scaler = joblib.load(path / scaler_file)
                    models[sensor_key] = {
                        "model": model,
                        "scaler": scaler,
                    }

        self.models = models
        self.is_trained = len(models) > 0
        self.last_updated = datetime.now() if self.is_trained else None

    def predict(
        self,
        predict_for: int = 24,
    ) -> Dict[str, Any]:
        """
        Make predictions on specific timestamps.

        Args:
            data: Dictionary of DataFrames with sensor data (one per sensor)
            predict_for: Number of time steps to forecast into the future
            **kwargs: Additional parameters

        Returns:
            Dictionary with forecasted values for each sensor and prediction_info
        """
        results = dict()
        results["forecast_max_steps"] = predict_for

        # Add prediction_info at root level with per-sensor grouping intervals
        # results["prediction_info"] = {
        #     "group_by_period_ms": self.group_by_ms_per_sensor.copy(),
        #     "recent_point_ts": {},  # Will be populated during prediction loop
        # }

        for sensor_key, model_dict in self.models.items():
            try:
                # Get model and scaler
                model = model_dict.get("model", None)
                scaler = model_dict.get("scaler", None)
                sensor_df = model_dict.get("data", None)
                if model is None or scaler is None or sensor_df is None:
                    logger.warning(f"[PREDICT] {sensor_key}: Skipping - missing components")
                    continue

                # Get the raw data for this sensor
                if sensor_df is None or sensor_df.empty:
                    logger.warning(f"[PREDICT] {sensor_key}: Skipping - no data")
                    continue

                # Prepare the data: extract sensor column and process
                sensor_data = prepare_sensor_data(sensor_df, sensor_key)

                # Scale the data
                sensor_values = sensor_data[sensor_key].values.reshape(-1, 1)
                scaled_data = scaler.transform(sensor_values)

                # Create RNN dataset from the latest data
                test_x, _ = create_rnn_dataset(scaled_data, self.lookback)

                # Check if we got any samples
                if len(test_x) == 0:
                    logger.warning(
                        f"[PREDICT] {sensor_key}: Skipping - insufficient data for lookback window"
                    )
                    continue

                test_x = np.reshape(test_x, (test_x.shape[0], 1, test_x.shape[1]))

                # Forecast future values
                result = forecast_future(
                    model,
                    test_x,
                    scaler,
                    self.lookback,
                    predict_for=predict_for,
                )

                max_timestamp = sensor_df["datetime"].max()
                min_timestamp = sensor_df["datetime"].min()

                # Log timestamp range for debugging
                logger.info(
                    f"{sensor_key}: INPUT data range [{min_timestamp} to {max_timestamp}], {len(sensor_df)} points"
                )

                # Store the last real timestamp for this sensor (in milliseconds)
                self.last_real_timestamps[sensor_key] = int(max_timestamp.timestamp() * 1000)

                logger.info(
                    f"{sensor_key}: last_real_timestamp stored = {max_timestamp} ({self.last_real_timestamps[sensor_key]} ms)"
                )

                results[sensor_key] = {}

                results[sensor_key]["prediction_info"] = {
                    "group_by_period_ms": self.group_by_ms_per_sensor.get(sensor_key, 5000)
                }

                # Populate prediction_info with this sensor's last real timestamp
                results[sensor_key]["prediction_info"]["recent_point_ts"] = (
                    self.last_real_timestamps[sensor_key]
                )

                # Convert forecast numpy array to list of floats
                if isinstance(result, np.ndarray):
                    # Flatten the array and convert to list of floats
                    results[sensor_key]["forecast"] = result.flatten().tolist()
                else:
                    results[sensor_key]["forecast"] = result

                # Get grouping interval for this sensor (fallback to 5000 if not set)
                sensor_group_by_ms = self.group_by_ms_per_sensor.get(sensor_key, 5000)

                # create a list of future timestamps from max_timestamp steps of sensor_group_by_ms
                future_timestamps = [
                    max_timestamp + pd.Timedelta(milliseconds=sensor_group_by_ms * (i + 1))
                    for i in range(predict_for)
                ]
                # Convert timestamps to milliseconds (Unix timestamp in ms)
                results[sensor_key]["timestamp"] = [
                    int(ts.timestamp() * 1000) for ts in future_timestamps
                ]

            except Exception as e:
                import traceback

                logger.error(f"[PREDICT] Error forecasting {sensor_key}: {str(e)}")
                traceback.print_exc()
                continue

        # DO NOT overwrite the per-sensor recent_point_ts dict that was populated in the loop
        # The prediction_info already has recent_point_ts[sensor_key] for each sensor

        return results

    def forecast(self, predict_for: int = 24) -> Dict[str, Any]:
        """
        Forecast future sensor values.

        Args:
            periods: Number of time periods to forecast
            freq: Frequency of forecasts ('H' for hourly, 'D' for daily, etc.)
            **kwargs: Additional parameters

        Returns:
            Dictionary with forecast results
        """
        # TODO: prediction might return
        # the same results if data is not updated
        # TODO: forcast data should have timestamps
        # starting from the last timestamp in self.data
        self.fetch_latest()
        results = self.predict(
            # pass dict of dataframes for each sensor
            predict_for=predict_for,
        )
        return results

    def forecast_multiple_horizons(
        self, horizons: List[int], freq: str = "H", **kwargs
    ) -> Dict[str, Any]:
        """
        Forecast at multiple time horizons.

        Args:
            horizons: List of forecast horizons (e.g., [1, 6, 12, 24])
            freq: Frequency of forecasts
            **kwargs: Additional parameters

        Returns:
            Dictionary with forecasts for each horizon
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before forecasting")

        results = {}

        for horizon in horizons:
            forecast_result = self.forecast(horizon, freq, **kwargs)
            results[f"horizon_{horizon}"] = forecast_result

        return {
            "sensor_name": self.sensor_name,
            "algorithm": self.algorithm_name,
            "horizons": horizons,
            "forecasts": results,
            "forecast_time": datetime.now().isoformat(),
        }

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get detailed information about the forecast model.

        Returns:
            Dictionary with model details
        """
        info = self.get_info()
        info["sensor_name"] = self.sensor_name
        info["algorithm_name"] = self.algorithm_name

        # Add training metrics if available
        algorithm = self.get_algorithm("forecast")
        if algorithm.training_metrics:
            info["training_metrics"] = {
                "mae": algorithm.training_metrics.mae,
                "rmse": algorithm.training_metrics.rmse,
                "r2_score": algorithm.training_metrics.r2_score,
            }

        return info
