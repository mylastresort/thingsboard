"""
Anomaly detection trainer - trains RF/XGB models and exports to ONNX.

This is a thin Python layer that:
1. Trains the anomaly detection models (RandomForest/XGBoost)
2. Exports them to ONNX format for Rust inference
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

from .onnx_exporter import OnnxExporter


class AnomalyTrainer:
    """
    Trains anomaly detection models and exports to ONNX.

    The Rust inference service loads these ONNX models directly.
    This Python layer is ONLY used for training.
    """

    SENSORS = ["volt", "rotate", "pressure", "vibration"]
    ERROR_KEYS = ["error1", "error2", "error3", "error4", "error5"]
    COMPONENT_KEYS = ["comp1", "comp2", "comp3", "comp4"]
    PREDICTION_HORIZONS = [1, 4, 8, 12, 16, 20, 24]

    def __init__(
        self,
        algorithm_name: str = "random_forest",
        hyperparameters: Optional[Dict[str, Any]] = None,
        random_state: int = 42,
    ):
        self.algorithm_name = algorithm_name
        self.hyperparameters = hyperparameters or {}
        self.random_state = random_state
        self.feature_columns: List[str] = []

    def _build_feature_columns(self) -> List[str]:
        """Build the 26-feature column list matching the Rust feature engineering."""
        features = []
        for key in self.SENSORS:
            features.extend([f"{key}mean_3h", f"{key}sd_3h", f"{key}mean_24h", f"{key}sd_24h"])
        for i in range(1, len(self.ERROR_KEYS) + 1):
            features.append(f"error{i}count")
        features.extend(self.COMPONENT_KEYS)
        features.append("age")
        return features

    def _create_targets(
        self, df: pd.DataFrame, hours_ahead: int
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Create binary and multiclass targets for a given prediction horizon.

        Returns (binary_target, multiclass_target).
        """
        future_failure = df.groupby("machineID")["failure"].transform(
            lambda x: x.shift(-hours_ahead).fillna(0).astype(int)
        )
        binary_target = (future_failure > 0).astype(int)

        multiclass_target = future_failure.copy()
        multiclass_target[binary_target == 0] = "none"

        return binary_target, multiclass_target

    def train(
        self,
        telemetry_df: pd.DataFrame,
        failures_df: pd.DataFrame,
        maintenance_df: pd.DataFrame,
        machines_df: pd.DataFrame,
        errors_df: pd.DataFrame,
        output_dir: Path,
    ) -> Dict[str, Any]:
        """
        Train all anomaly models (7 horizons x 2 types = 14 models) and export to ONNX.

        Returns metadata about exported models.
        """
        self.feature_columns = self._build_feature_columns()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        all_metadata = {"models": {}, "scalers": {}, "encoders": {}}

        # Prepare features (same logic as AnomalyPredictor.preprocess_data)
        features_df = self._prepare_features(
            telemetry_df, failures_df, maintenance_df, machines_df, errors_df
        )

        label_encoder = LabelEncoder()
        label_encoder.fit(
            np.array(self.COMPONENT_KEYS + ["none"])
        )

        # Export label encoder
        OnnxExporter.export_label_encoder(
            label_encoder, output_dir, "label_encoder"
        )

        for horizon in self.PREDICTION_HORIZONS:
            binary_target, multiclass_target = self._create_targets(features_df, horizon)

            # Drop rows with NaN targets
            valid_mask = multiclass_target.notna() & (multiclass_target != "")
            X = features_df.loc[valid_mask, self.feature_columns].values.astype(np.float32)
            y_binary = binary_target.loc[valid_mask].values
            y_multi = multiclass_target.loc[valid_mask].values

            if len(X) < 10:
                continue

            # Train binary classifier
            binary_model = self._create_model()
            binary_model.fit(X, y_binary)

            OnnxExporter.export_sklearn_model(
                binary_model,
                X,
                output_dir,
                model_name=f"hour_{horizon}_binary",
                input_names=self.feature_columns,
            )

            # Train multiclass classifier
            multi_model = self._create_model()
            multi_model.fit(X, y_multi)

            OnnxExporter.export_sklearn_model(
                multi_model,
                X,
                output_dir,
                model_name=f"hour_{horizon}_multiclass",
                input_names=self.feature_columns,
            )

            all_metadata["models"][f"hour_{horizon}"] = {
                "binary": f"hour_{horizon}_binary",
                "multiclass": f"hour_{horizon}_multiclass",
                "n_features": len(self.feature_columns),
            }

        # Save feature columns and config
        config = {
            "feature_columns": self.feature_columns,
            "sensors": self.SENSORS,
            "error_keys": self.ERROR_KEYS,
            "component_keys": self.COMPONENT_KEYS,
            "prediction_horizons": self.PREDICTION_HORIZONS,
            "algorithm": self.algorithm_name,
        }
        with open(output_dir / "config.json", "w") as f:
            json.dump(config, f, indent=2)

        all_metadata["config"] = config

        meta_path = output_dir / "training_metadata.json"
        with open(meta_path, "w") as f:
            json.dump(all_metadata, f, indent=2, default=str)

        return all_metadata

    def _create_model(self):
        """Create a model instance based on algorithm_name."""
        if self.algorithm_name == "xgboost":
            return XGBClassifier(
                random_state=self.random_state,
                **self.hyperparameters,
            )
        else:
            return RandomForestClassifier(
                random_state=self.random_state,
                **self.hyperparameters,
            )

    def _prepare_features(
        self,
        telemetry_df: pd.DataFrame,
        failures_df: pd.DataFrame,
        maintenance_df: pd.DataFrame,
        machines_df: pd.DataFrame,
        errors_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Prepare features matching the Rust feature engineering.
        This is the Python reference implementation.
        """
        # Compute rolling stats per sensor
        for key in self.SENSORS:
            for window, suffix in [(3, "3h"), (24, "24h")]:
                telemetry_df[f"{key}mean_{suffix}"] = (
                    telemetry_df.groupby("machineID")[key]
                    .transform(lambda x: x.rolling(window, min_periods=1).mean())
                )
                telemetry_df[f"{key}sd_{suffix}"] = (
                    telemetry_df.groupby("machineID")[key]
                    .transform(lambda x: x.rolling(window, min_periods=1).std().fillna(0))
                )

        # Count errors per type
        for i, err_key in enumerate(self.ERROR_KEYS, 1):
            telemetry_df[f"error{i}count"] = 0

        if not errors_df.empty and "errorID" in errors_df.columns:
            error_counts = (
                errors_df.groupby(["machineID", "errorID"])
                .size()
                .unstack(fill_value=0)
            )
            for i, err_key in enumerate(self.ERROR_KEYS, 1):
                if err_key in error_counts.columns:
                    telemetry_df[f"error{i}count"] = telemetry_df["machineID"].map(
                        error_counts[err_key]
                    ).fillna(0).astype(int)

        # Component days since replacement
        for comp in self.COMPONENT_KEYS:
            telemetry_df[f"{comp}_days"] = 0

        if not maintenance_df.empty and "comp" in maintenance_df.columns:
            for comp in self.COMPONENT_KEYS:
                comp_maint = maintenance_df[maintenance_df["comp"] == comp].copy()
                if not comp_maint.empty and "datetime" in comp_maint.columns:
                    comp_maint["datetime"] = pd.to_datetime(comp_maint["datetime"])
                    last_repl = comp_maint.groupby("machineID")["datetime"].max()
                    if "datetime" in telemetry_df.columns:
                        telemetry_df["datetime"] = pd.to_datetime(telemetry_df["datetime"])
                        telemetry_df[f"{comp}_days"] = (
                            telemetry_df["datetime"]
                            - telemetry_df["machineID"].map(last_repl)
                        ).dt.days.fillna(999).astype(int)

        # Machine age
        if "age" in machines_df.columns and "machineID" in machines_df.columns:
            age_map = machines_df.set_index("machineID")["age"].to_dict()
            telemetry_df["age"] = telemetry_df["machineID"].map(age_map).fillna(0)
        else:
            telemetry_df["age"] = 0

        return telemetry_df
