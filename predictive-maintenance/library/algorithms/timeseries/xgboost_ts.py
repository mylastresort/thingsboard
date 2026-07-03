"""
XGBoost-based time series forecasting adapter.
"""

import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from ...core.algorithm_interface import BaseAlgorithm
from ...core.types import (
    AlgorithmCapabilities,
    ForecastOutput,
    PredictionOutput,
    TimeSeriesConfig,
    TrainingMetrics,
)


class XGBoostTimeSeriesAdapter(BaseAlgorithm):
    """Adapter for XGBoost-based time series forecasting using lagged features"""

    def __init__(self, config: TimeSeriesConfig):
        super().__init__(config)
        self.config: TimeSeriesConfig = config
        self.last_values: Optional[np.ndarray] = None
        self.last_timestamp: Optional[datetime] = None

    def _define_capabilities(self) -> AlgorithmCapabilities:
        return AlgorithmCapabilities(
            supports_classification=False,
            supports_regression=False,
            supports_time_series=True,
            supports_feature_importance=True,
            supports_probability=False,
            supports_incremental_learning=True,
            requires_scaling=False,
            handles_missing_values=True,
            handles_categorical=False,
        )

    def _create_lagged_features(self, df: pd.DataFrame, n_lags: int = 24) -> pd.DataFrame:
        """
        Create lagged features for time series forecasting.

        Args:
            df: DataFrame with time series data
            n_lags: Number of lag features to create
        """
        df = df.copy()

        # Create lag features
        for i in range(1, n_lags + 1):
            df[f"lag_{i}"] = df[self.config.value_column].shift(i)

        # Create rolling statistics
        for window in [6, 12, 24]:
            df[f"rolling_mean_{window}"] = (
                df[self.config.value_column].shift(1).rolling(window).mean()
            )
            df[f"rolling_std_{window}"] = (
                df[self.config.value_column].shift(1).rolling(window).std()
            )

        # Create time-based features
        df["hour"] = pd.to_datetime(df[self.config.time_column]).dt.hour
        df["day_of_week"] = pd.to_datetime(df[self.config.time_column]).dt.dayofweek
        df["day_of_month"] = pd.to_datetime(df[self.config.time_column]).dt.day
        df["month"] = pd.to_datetime(df[self.config.time_column]).dt.month

        # Drop rows with NaN values
        df = df.dropna()

        return df

    def train(self, X: pd.DataFrame, y: Optional[pd.Series] = None) -> TrainingMetrics:
        """
        Train XGBoost model on time series data.

        Expected data format:
        - X must have time_column and value_column specified in config
        """
        start_time = time.time()

        # Create lagged features
        n_lags = self.config.hyperparameters.get("n_lags", 24)
        df = self._create_lagged_features(X, n_lags)

        # Prepare features and target
        feature_cols = [
            col
            for col in df.columns
            if col not in [self.config.time_column, self.config.value_column]
        ]
        X_features = df[feature_cols]
        y_target = df[self.config.value_column]

        # Split data
        test_size = self.config.hyperparameters.get("test_size", 0.2)
        X_train, X_test, y_train, y_test = train_test_split(
            X_features,
            y_target,
            test_size=test_size,
            shuffle=False,  # Important for time series
        )

        # Create and train model
        self.model = xgb.XGBRegressor(
            random_state=self.config.random_state,
            **{
                k: v
                for k, v in self.config.hyperparameters.items()
                if k not in ["n_lags", "test_size"]
            },
        )

        self.model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
        self.is_trained = True

        # Store last values for future forecasting
        self.last_values = df[self.config.value_column].tail(n_lags).values
        self.last_timestamp = pd.to_datetime(df[self.config.time_column].iloc[-1])

        # Make predictions
        y_pred = self.model.predict(X_test)

        # Calculate metrics
        metrics = TrainingMetrics(training_time=time.time() - start_time)
        metrics.rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        metrics.mae = float(mean_absolute_error(y_test, y_pred))
        metrics.r2_score = float(r2_score(y_test, y_pred))

        # Feature importance
        if hasattr(self.model, "feature_importances_"):
            metrics.feature_importances = dict(
                zip(feature_cols, self.model.feature_importances_.tolist())
            )

        self.training_metrics = metrics
        return metrics

    def predict(self, X: pd.DataFrame) -> PredictionOutput:
        """Make predictions on new data"""
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions")

        # Create lagged features
        n_lags = self.config.hyperparameters.get("n_lags", 24)
        df = self._create_lagged_features(X, n_lags)

        # Prepare features
        feature_cols = [
            col
            for col in df.columns
            if col not in [self.config.time_column, self.config.value_column]
        ]
        X_features = df[feature_cols]

        # Make predictions
        predictions = self.model.predict(X_features)

        return PredictionOutput(
            predictions=predictions,
            metadata={"algorithm": "xgboost_ts", "n_samples": len(predictions)},
        )

    def forecast(self, periods: int, freq: str = "H", **kwargs) -> ForecastOutput:
        """
        Make future forecasts using iterative prediction.

        Args:
            periods: Number of time periods to forecast
            freq: Frequency of forecasts ('H' for hourly, 'D' for daily, etc.)
        """
        if not self.is_trained or self.last_values is None or self.last_timestamp is None:
            raise ValueError("Model must be trained before forecasting")

        n_lags = self.config.hyperparameters.get("n_lags", 24)
        forecasts = []
        timestamps = []

        # Initialize with last known values
        recent_values = list(self.last_values)
        current_time = self.last_timestamp

        # Frequency mapping
        freq_map = {
            "H": timedelta(hours=1),
            "D": timedelta(days=1),
            "T": timedelta(minutes=1),
        }
        time_delta = freq_map.get(freq, timedelta(hours=1))

        for _ in range(periods):
            # Move to next timestamp
            current_time = current_time + time_delta
            timestamps.append(current_time)

            # Create features for this prediction
            features = {}

            # Lag features
            for i in range(1, n_lags + 1):
                features[f"lag_{i}"] = recent_values[-i] if i <= len(recent_values) else 0

            # Rolling statistics
            for window in [6, 12, 24]:
                if len(recent_values) >= window:
                    features[f"rolling_mean_{window}"] = np.mean(recent_values[-window:])
                    features[f"rolling_std_{window}"] = np.std(recent_values[-window:])
                else:
                    features[f"rolling_mean_{window}"] = np.mean(recent_values)
                    features[f"rolling_std_{window}"] = 0

            # Time features
            features["hour"] = current_time.hour
            features["day_of_week"] = current_time.weekday()
            features["day_of_month"] = current_time.day
            features["month"] = current_time.month

            # Make prediction
            X_pred = pd.DataFrame([features])
            prediction = self.model.predict(X_pred)[0]

            forecasts.append(prediction)
            recent_values.append(prediction)

        return ForecastOutput(
            timestamps=timestamps,
            forecasted_values=np.array(forecasts),
            metadata={"algorithm": "xgboost_ts", "freq": freq, "periods": periods},
        )

    def get_feature_importance(self) -> Optional[dict[str, float]]:
        """Get feature importance from trained model"""
        if not self.is_trained or not hasattr(self.model, "feature_importances_"):
            return None

        if self.training_metrics and self.training_metrics.feature_importances:
            return self.training_metrics.feature_importances

        return None
