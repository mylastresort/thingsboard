"""
Core types and data structures used across the library.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np


class AlgorithmType(str, Enum):
    """Types of machine learning algorithms"""

    SUPERVISED = "supervised"
    TIME_SERIES = "time_series"
    NEURAL_NETWORK = "neural_network"


class TaskType(str, Enum):
    """Machine learning task types"""

    BINARY_CLASSIFICATION = "binary_classification"
    MULTICLASS_CLASSIFICATION = "multiclass_classification"
    REGRESSION = "regression"
    TIME_SERIES_FORECAST = "time_series_forecast"
    ANOMALY_DETECTION = "anomaly_detection"


@dataclass
class AlgorithmConfig:
    """Base configuration for all algorithms"""

    name: str
    algorithm_type: AlgorithmType
    task_type: TaskType
    random_state: int = 42
    hyperparameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "algorithm_type": self.algorithm_type.value,
            "task_type": self.task_type.value,
            "random_state": self.random_state,
            "hyperparameters": self.hyperparameters,
        }


@dataclass
class SupervisedConfig(AlgorithmConfig):
    """Configuration for supervised learning algorithms"""

    feature_columns: List[str] = field(default_factory=list)
    target_column: Optional[str] = None
    test_size: float = 0.2
    cv_folds: int = 5

    def __post_init__(self):
        if self.algorithm_type not in [
            AlgorithmType.SUPERVISED,
            AlgorithmType.NEURAL_NETWORK,
        ]:
            self.algorithm_type = AlgorithmType.SUPERVISED


@dataclass
class TimeSeriesConfig(AlgorithmConfig):
    """Configuration for time series forecasting algorithms"""

    time_column: str = "timestamp"
    value_column: str = "value"
    forecast_horizon: int = 24  # hours
    seasonality_mode: str = "multiplicative"
    changepoint_prior_scale: float = 0.05

    def __post_init__(self):
        self.algorithm_type = AlgorithmType.TIME_SERIES
        self.task_type = TaskType.TIME_SERIES_FORECAST


@dataclass
class NeuralNetworkConfig(AlgorithmConfig):
    """Configuration for neural network algorithms"""

    hidden_layers: List[int] = field(default_factory=lambda: [64, 32])
    activation: str = "relu"
    optimizer: str = "adam"
    learning_rate: float = 0.001
    batch_size: int = 32
    epochs: int = 100
    early_stopping_patience: int = 10

    def __post_init__(self):
        self.algorithm_type = AlgorithmType.NEURAL_NETWORK


@dataclass
class PredictionOutput:
    """Output from a prediction operation"""

    predictions: np.ndarray
    probabilities: Optional[np.ndarray] = None
    prediction_time: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predictions": (
                self.predictions.tolist()
                if isinstance(self.predictions, np.ndarray)
                else self.predictions
            ),
            "probabilities": (
                self.probabilities.tolist()
                if isinstance(self.probabilities, np.ndarray)
                else self.probabilities
            ),
            "prediction_time": self.prediction_time.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class TrainingMetrics:
    """Metrics from model training"""

    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    roc_auc: Optional[float] = None
    rmse: Optional[float] = None
    mae: Optional[float] = None
    r2_score: Optional[float] = None
    training_time: float = 0.0
    cross_val_scores: Optional[List[float]] = None
    confusion_matrix: Optional[np.ndarray] = None
    feature_importances: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "roc_auc": self.roc_auc,
            "rmse": self.rmse,
            "mae": self.mae,
            "r2_score": self.r2_score,
            "training_time": self.training_time,
            "cross_val_scores": self.cross_val_scores,
            "confusion_matrix": (
                self.confusion_matrix.tolist()
                if isinstance(self.confusion_matrix, np.ndarray)
                else None
            ),
            "feature_importances": self.feature_importances,
        }


@dataclass
class ForecastOutput:
    """Output from a forecast operation"""

    timestamps: List[datetime]
    forecasted_values: np.ndarray
    lower_bound: Optional[np.ndarray] = None
    upper_bound: Optional[np.ndarray] = None
    confidence_level: float = 0.95
    forecast_time: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamps": [ts.isoformat() for ts in self.timestamps],
            "forecasted_values": (
                self.forecasted_values.tolist()
                if isinstance(self.forecasted_values, np.ndarray)
                else self.forecasted_values
            ),
            "lower_bound": (
                self.lower_bound.tolist() if isinstance(self.lower_bound, np.ndarray) else None
            ),
            "upper_bound": (
                self.upper_bound.tolist() if isinstance(self.upper_bound, np.ndarray) else None
            ),
            "confidence_level": self.confidence_level,
            "forecast_time": self.forecast_time.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class AlgorithmCapabilities:
    """Describes what an algorithm can do"""

    supports_classification: bool = False
    supports_regression: bool = False
    supports_time_series: bool = False
    supports_feature_importance: bool = False
    supports_probability: bool = False
    supports_incremental_learning: bool = False
    requires_scaling: bool = True
    handles_missing_values: bool = False
    handles_categorical: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supports_classification": self.supports_classification,
            "supports_regression": self.supports_regression,
            "supports_time_series": self.supports_time_series,
            "supports_feature_importance": self.supports_feature_importance,
            "supports_probability": self.supports_probability,
            "supports_incremental_learning": self.supports_incremental_learning,
            "requires_scaling": self.requires_scaling,
            "handles_missing_values": self.handles_missing_values,
            "handles_categorical": self.handles_categorical,
        }
