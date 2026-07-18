"""
ONNX model exporter - converts trained sklearn/XGBoost/Keras models to ONNX format.

This is the bridge between Python training and Rust inference.
All models are exported to ONNX which Rust loads via the ort crate.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class OnnxExporter:
    """Exports trained models to ONNX format for Rust inference."""

    @staticmethod
    def export_sklearn_model(
        model: Any,
        X_sample: np.ndarray,
        output_path: Path,
        model_name: str = "model",
        input_names: Optional[List[str]] = None,
        target_opset: int = 13,
    ) -> Dict[str, Any]:
        """
        Export a scikit-learn model to ONNX.

        Returns metadata dict with input/output specs for Rust loading.
        """
        from skl2onnx import to_onnx
        from skl2onnx.common.data_types import FloatTensorType

        initial_types = [
            ("input", FloatTensorType([None, X_sample.shape[1]]))
        ]

        onx = to_onnx(model, X_sample[:1], target_opset=target_opset)

        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        onnx_path = output_path / f"{model_name}.onnx"

        with open(onnx_path, "wb") as f:
            f.write(onx.SerializeToString())

        metadata = {
            "model_name": model_name,
            "model_type": "sklearn",
            "format": "onnx",
            "onnx_path": str(onnx_path),
            "input_shape": [None, X_sample.shape[1]],
            "input_dtype": "float32",
            "input_names": input_names or [f"feature_{i}" for i in range(X_sample.shape[1])],
            "n_features": X_sample.shape[1],
        }

        meta_path = output_path / f"{model_name}_meta.json"
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return metadata

    @staticmethod
    def export_xgboost_model(
        model: Any,
        X_sample: np.ndarray,
        output_path: Path,
        model_name: str = "model",
        input_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Export an XGBoost model to ONNX.

        XGBoost has native ONNX export via onnxmltools.
        """
        from onnxmltools.convert import convert_xgboost
        from onnxmltools.convert.common.data_types import FloatTensorType
        from onnxmltools.convert.xgboost.operator_converters.XGBoost import convert_xgboost as convert_xgboost_impl

        initial_types = [
            ("input", FloatTensorType([None, X_sample.shape[1]]))
        ]

        # For XGBClassifier/XGBRegressor with scikit-learn API
        from skl2onnx import convert_sklearn, update_registered_converter
        from skl2onnx.common.shape_calculator import (
            calculate_linear_classifier_output_shapes,
            calculate_linear_regressor_output_shapes,
        )

        model_class = type(model).__name__
        if "Classifier" in model_class:
            update_registered_converter(
                type(model),
                f"XGBoost{model_class}",
                calculate_linear_classifier_output_shapes,
                convert_xgboost_impl,
                options={"nocl": [True, False], "zipmap": [True, False, "columns"]},
            )
        elif "Regressor" in model_class:
            update_registered_converter(
                type(model),
                f"XGBoost{model_class}",
                calculate_linear_regressor_output_shapes,
                convert_xgboost_impl,
            )

        model_onnx = convert_sklearn(
            model,
            model_name,
            initial_types,
            target_opset={"": 13, "ai.onnx.ml": 2},
        )

        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        onnx_path = output_path / f"{model_name}.onnx"

        with open(onnx_path, "wb") as f:
            f.write(model_onnx.SerializeToString())

        metadata = {
            "model_name": model_name,
            "model_type": "xgboost",
            "format": "onnx",
            "onnx_path": str(onnx_path),
            "input_shape": [None, X_sample.shape[1]],
            "input_dtype": "float32",
            "input_names": input_names or [f"feature_{i}" for i in range(X_sample.shape[1])],
            "n_features": X_sample.shape[1],
        }

        meta_path = output_path / f"{model_name}_meta.json"
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return metadata

    @staticmethod
    def export_keras_model(
        model: Any,
        output_path: Path,
        model_name: str = "model",
        input_signature: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Export a Keras/TF model to ONNX via tf2onnx.

        For LSTM and other neural network models.
        """
        import tensorflow as tf
        import tf2onnx

        if input_signature is None:
            # Infer from model input shape
            input_shape = model.input_shape
            input_signature = [
                tf.TensorSpec(
                    shape=input_shape[1:],
                    dtype=tf.float32,
                    name="input",
                )
            ]

        model_proto, _ = tf2onnx.convert.from_keras(
            model,
            input_signature=input_signature,
            opset=13,
        )

        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        onnx_path = output_path / f"{model_name}.onnx"

        with open(onnx_path, "wb") as f:
            f.write(model_proto.SerializeToString())

        input_shape = list(model.input_shape[1:])
        metadata = {
            "model_name": model_name,
            "model_type": "keras",
            "format": "onnx",
            "onnx_path": str(onnx_path),
            "input_shape": [None] + input_shape,
            "input_dtype": "float32",
            "input_names": ["input"],
            "n_features": input_shape[-1] if len(input_shape) > 0 else 0,
        }

        meta_path = output_path / f"{model_name}_meta.json"
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return metadata

    @staticmethod
    def export_scaler(
        scaler: Any,
        output_path: Path,
        scaler_name: str = "scaler",
    ) -> Dict[str, Any]:
        """Export a StandardScaler as JSON for Rust to load."""
        import joblib

        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        # Extract scaler parameters
        if hasattr(scaler, "mean_") and hasattr(scaler, "scale_"):
            params = {
                "type": "standard",
                "mean": scaler.mean_.tolist(),
                "scale": scaler.scale_.tolist(),
                "var": scaler.var_.tolist() if hasattr(scaler, "var_") else None,
                "n_features_in": int(scaler.n_features_in_) if hasattr(scaler, "n_features_in_") else len(scaler.mean_),
            }
        else:
            # Fallback: pickle the scaler
            scaler_path = output_path / f"{scaler_name}.pkl"
            joblib.dump(scaler, scaler_path)
            params = {
                "type": "joblib",
                "path": str(scaler_path),
            }

        meta_path = output_path / f"{scaler_name}_meta.json"
        with open(meta_path, "w") as f:
            json.dump(params, f, indent=2)

        return params

    @staticmethod
    def export_label_encoder(
        encoder: Any,
        output_path: Path,
        encoder_name: str = "label_encoder",
    ) -> Dict[str, Any]:
        """Export a LabelEncoder as JSON for Rust to load."""
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        params = {
            "type": "label_encoder",
            "classes": encoder.classes_.tolist(),
        }

        meta_path = output_path / f"{encoder_name}_meta.json"
        with open(meta_path, "w") as f:
            json.dump(params, f, indent=2)

        return params
