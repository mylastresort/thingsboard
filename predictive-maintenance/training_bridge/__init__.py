"""
Training bridge: thin Python layer that trains models and exports to ONNX.

This module is the ONLY Python code that touches ML frameworks.
The Rust inference service loads the exported ONNX models directly.
"""

from .onnx_exporter import OnnxExporter
from .anomaly_trainer import AnomalyTrainer
from .forecast_trainer import ForecastTrainer

__all__ = ["OnnxExporter", "AnomalyTrainer", "ForecastTrainer"]
