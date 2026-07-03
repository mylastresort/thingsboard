"""
Core module - Base interfaces and types for the library
"""

from .algorithm_interface import AlgorithmType, BaseAlgorithm, TaskType
from .model_interface import BaseModel
from .types import (
    AlgorithmCapabilities,
    AlgorithmConfig,
    ForecastOutput,
    NeuralNetworkConfig,
    PredictionOutput,
    SupervisedConfig,
    TimeSeriesConfig,
    TrainingMetrics,
)

__all__ = [
    "BaseAlgorithm",
    "BaseModel",
    "AlgorithmType",
    "TaskType",
    "AlgorithmConfig",
    "SupervisedConfig",
    "TimeSeriesConfig",
    "NeuralNetworkConfig",
    "PredictionOutput",
    "TrainingMetrics",
    "ForecastOutput",
    "AlgorithmCapabilities",
]
