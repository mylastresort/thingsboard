"""
Base algorithm interface - Abstract base class for all ML algorithms.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from .types import (
    AlgorithmCapabilities,
    AlgorithmConfig,
    AlgorithmType,
    ForecastOutput,
    PredictionOutput,
    TaskType,
    TrainingMetrics,
)


class BaseAlgorithm(ABC):
    """
    Abstract base class for all machine learning algorithms.
    Provides a unified interface for training, prediction, and model management.
    """

    def __init__(self, config: AlgorithmConfig):
        """
        Initialize the algorithm with configuration.

        Args:
            config: Algorithm configuration
        """
        self.config = config
        self.model: Optional[Any] = None
        self.is_trained: bool = False
        self.training_metrics: Optional[TrainingMetrics] = None
        self._capabilities = self._define_capabilities()

    @abstractmethod
    def _define_capabilities(self) -> AlgorithmCapabilities:
        """Define what this algorithm can do"""
        pass

    @abstractmethod
    def train(self, X: pd.DataFrame, y: Optional[pd.Series] = None) -> TrainingMetrics:
        """
        Train the algorithm on the provided data.

        Args:
            X: Feature data
            y: Target data (optional for unsupervised learning)

        Returns:
            TrainingMetrics with training results
        """
        pass

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> PredictionOutput:
        """
        Make predictions on new data.

        Args:
            X: Feature data

        Returns:
            PredictionOutput with predictions and metadata
        """
        pass

    def forecast(self, periods: int, **kwargs) -> ForecastOutput:
        """
        Make forecasts (for time series algorithms).

        Args:
            periods: Number of time periods to forecast
            **kwargs: Additional algorithm-specific parameters

        Returns:
            ForecastOutput with forecasted values

        Raises:
            NotImplementedError: If algorithm doesn't support forecasting
        """
        if not self._capabilities.supports_time_series:
            raise NotImplementedError(
                f"{self.__class__.__name__} does not support time series forecasting"
            )
        raise NotImplementedError("Subclass must implement forecast method")

    def get_feature_importance(self) -> Optional[Dict[str, float]]:
        """
        Get feature importance scores.

        Returns:
            Dictionary mapping feature names to importance scores, or None if not available
        """
        if not self._capabilities.supports_feature_importance:
            return None
        return None

    def save(self, path: Path) -> None:
        """
        Save the trained model to disk.

        Args:
            path: Path where to save the model
        """
        import joblib

        if not self.is_trained:
            raise ValueError("Cannot save untrained model")

        model_data = {
            "model": self.model,
            "config": self.config,
            "training_metrics": self.training_metrics,
            "capabilities": self._capabilities,
        }
        joblib.dump(model_data, path)

    def load(self, path: Path) -> None:
        """
        Load a trained model from disk.

        Args:
            path: Path to the saved model
        """
        import joblib

        model_data = joblib.load(path)

        self.model = model_data["model"]
        self.config = model_data["config"]
        self.training_metrics = model_data.get("training_metrics")
        self._capabilities = model_data.get("capabilities", self._define_capabilities())
        self.is_trained = True

    @property
    def capabilities(self) -> AlgorithmCapabilities:
        """Get algorithm capabilities"""
        return self._capabilities

    @property
    def algorithm_type(self) -> AlgorithmType:
        """Get algorithm type"""
        return self.config.algorithm_type

    @property
    def task_type(self) -> TaskType:
        """Get task type"""
        return self.config.task_type

    def __repr__(self) -> str:
        status = "trained" if self.is_trained else "untrained"
        return f"{self.__class__.__name__}(name='{self.config.name}', status='{status}')"
