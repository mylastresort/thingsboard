"""
Forecast trainer - trains LSTM/XGBoost models and exports to ONNX.

This is a thin Python layer that:
1. Trains the forecast models (LSTM via Keras or XGBoost)
2. Exports them to ONNX format for Rust inference
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from .onnx_exporter import OnnxExporter


class ForecastTrainer:
    """
    Trains time-series forecast models and exports to ONNX.

    The Rust inference service loads these ONNX models directly.
    This Python layer is ONLY used for training.
    """

    def __init__(
        self,
        algorithm_name: str = "lstm",
        lookback_window: int = 20,
        epochs: int = 35,
        batch_size: int = 128,
        random_state: int = 42,
    ):
        self.algorithm_name = algorithm_name
        self.lookback_window = lookback_window
        self.epochs = epochs
        self.batch_size = batch_size
        self.random_state = random_state

    def train(
        self,
        sensor_data: Dict[str, pd.DataFrame],
        output_dir: Path,
        forecast_horizon: int = 10,
    ) -> Dict[str, Any]:
        """
        Train forecast models for each sensor and export to ONNX.

        Args:
            sensor_data: Dict mapping sensor_key -> DataFrame with timestamp, value columns
            output_dir: Where to save ONNX models and metadata
            forecast_horizon: How many steps to forecast

        Returns:
            Metadata about exported models
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        all_metadata = {"models": {}, "scalers": {}}

        for sensor_key, df in sensor_data.items():
            if df.empty or len(df) < self.lookback_window + 10:
                continue

            values = df["value"].values.astype(np.float32)
            timestamps = pd.to_datetime(df["timestamp"])

            # Scale
            scaler = StandardScaler()
            scaled_values = scaler.fit_transform(values.reshape(-1, 1)).flatten()

            # Export scaler
            OnnxExporter.export_scaler(scaler, output_dir, f"scaler_{sensor_key}")

            # Create sequences
            X, y = self._create_sequences(scaled_values)

            if len(X) < 20:
                continue

            if self.algorithm_name == "lstm":
                metadata = self._train_lstm(
                    X, y, sensor_key, output_dir, forecast_horizon
                )
            else:
                metadata = self._train_xgboost(
                    X, y, sensor_key, output_dir, forecast_horizon
                )

            metadata["scaler"] = f"scaler_{sensor_key}"
            all_metadata["models"][sensor_key] = metadata
            all_metadata["scalers"][sensor_key] = {
                "mean": scaler.mean_.tolist(),
                "scale": scaler.scale_.tolist(),
            }

        # Save config
        config = {
            "algorithm": self.algorithm_name,
            "lookback_window": self.lookback_window,
            "forecast_horizon": forecast_horizon,
            "sensors": list(sensor_data.keys()),
        }
        with open(output_dir / "config.json", "w") as f:
            json.dump(config, f, indent=2)

        all_metadata["config"] = config
        meta_path = output_dir / "training_metadata.json"
        with open(meta_path, "w") as f:
            json.dump(all_metadata, f, indent=2, default=str)

        return all_metadata

    def _create_sequences(
        self, values: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Create input/output sequences for time series training."""
        X, y = [], []
        for i in range(self.lookback_window, len(values)):
            X.append(values[i - self.lookback_window : i])
            y.append(values[i])
        return np.array(X), np.array(y)

    def _train_lstm(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sensor_key: str,
        output_dir: Path,
        forecast_horizon: int,
    ) -> Dict[str, Any]:
        """Train LSTM model and export to ONNX."""
        import tensorflow as tf
        from sklearn.model_selection import train_test_split

        # Reshape for LSTM: [samples, timesteps, features]
        X_lstm = X.reshape((X.shape[0], X.shape[1], 1))

        X_train, X_test, y_train, y_test = train_test_split(
            X_lstm, y, test_size=0.25, shuffle=False
        )

        # Build LSTM model (matching existing architecture)
        model = tf.keras.Sequential([
            tf.keras.layers.LSTM(256, input_shape=(self.lookback_window, 1)),
            tf.keras.layers.Dense(1),
        ])
        model.compile(optimizer="adam", loss="mse")

        # Mixed precision for GPU
        try:
            tf.keras.mixed_precision.set_global_policy("mixed_float16")
        except Exception:
            pass

        model.fit(
            X_train, y_train,
            validation_data=(X_test, y_test),
            epochs=self.epochs,
            batch_size=self.batch_size,
            verbose=0,
        )

        # Export to ONNX
        model_name = f"lstm_model_{sensor_key}"
        OnnxExporter.export_keras_model(
            model,
            output_dir,
            model_name=model_name,
            input_signature=[
                tf.TensorSpec(
                    shape=[None, self.lookback_window, 1],
                    dtype=tf.float32,
                    name="input",
                )
            ],
        )

        # Evaluate
        test_loss = model.evaluate(X_test, y_test, verbose=0)
        predictions = model.predict(X_test, verbose=0).flatten()
        rmse = float(np.sqrt(np.mean((predictions - y_test) ** 2)))
        mae = float(np.mean(np.abs(predictions - y_test)))

        return {
            "model_name": model_name,
            "model_type": "lstm",
            "format": "onnx",
            "rmse": rmse,
            "mae": mae,
            "test_loss": float(test_loss),
            "n_train": len(X_train),
            "n_test": len(X_test),
        }

    def _train_xgboost(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sensor_key: str,
        output_dir: Path,
        forecast_horizon: int,
    ) -> Dict[str, Any]:
        """Train XGBoost model and export to ONNX."""
        from sklearn.model_selection import train_test_split
        from xgboost import XGBRegressor

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.25, shuffle=False
        )

        model = XGBRegressor(random_state=self.random_state)
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        # Export to ONNX
        model_name = f"xgboost_forecast_{sensor_key}"
        OnnxExporter.export_xgboost_model(
            model,
            X_train,
            output_dir,
            model_name=model_name,
            input_names=[f"lag_{i+1}" for i in range(self.lookback_window)],
        )

        # Evaluate
        predictions = model.predict(X_test)
        rmse = float(np.sqrt(np.mean((predictions - y_test) ** 2)))
        mae = float(np.mean(np.abs(predictions - y_test)))

        return {
            "model_name": model_name,
            "model_type": "xgboost",
            "format": "onnx",
            "rmse": rmse,
            "mae": mae,
            "n_train": len(X_train),
            "n_test": len(X_test),
        }
