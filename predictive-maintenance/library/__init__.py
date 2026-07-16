__version__ = "1.0.0"

# Import main interfaces
# Import factory
from .algorithms.factory import AlgorithmRegistry
from .core.algorithm_interface import AlgorithmType, BaseAlgorithm, TaskType
from .core.model_interface import BaseModel
from .core.types import (
    AlgorithmConfig,
    ForecastOutput,
    PredictionOutput,
    SupervisedConfig,
    TimeSeriesConfig,
    TrainingMetrics,
)

# Import models
from .models.anomaly_predictor import AnomalyPredictor
from .models.forecast_model import ForecastModel

__all__ = [
    # Version
    "__version__",
    # Core interfaces
    "BaseAlgorithm",
    "BaseModel",
    "AlgorithmType",
    "TaskType",
    # Types
    "AlgorithmConfig",
    "SupervisedConfig",
    "TimeSeriesConfig",
    "PredictionOutput",
    "TrainingMetrics",
    "ForecastOutput",
    # Factory
    "AlgorithmRegistry",
    # Models
    "AnomalyPredictor",
    "ForecastModel",
]
