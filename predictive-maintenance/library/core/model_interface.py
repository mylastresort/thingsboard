"""
Base model interface - Abstract base class for business logic models.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .algorithm_interface import BaseAlgorithm


class BaseModel(ABC):
    """
    Abstract base class for business logic models.
    Models use algorithms to implement specific business functionality.
    """

    def __init__(self, name: str, data_registry=None):
        """
        Initialize the model.

        Args:
            name: Model name/identifier
            data_registry: Optional DataRegistry instance for database access
        """
        self.name = name
        self.data_registry = data_registry
        self.algorithms: Dict[str, BaseAlgorithm] = {}
        self.is_trained: bool = False
        self.created_at: datetime = datetime.now()
        self.last_updated: Optional[datetime] = None

    @abstractmethod
    def fetch(self, device_id: str, **kwargs) -> pd.DataFrame:
        """
        Fetch training data for this model type.

        Args:
            device_id: Device or model identifier
            **kwargs: Additional parameters (e.g., days_back, sensor_key)

        Returns:
            DataFrame with training data
        """
        pass

    @abstractmethod
    def fetch_latest(self, device_id: str, **kwargs) -> pd.DataFrame:
        """
        Fetch latest data for predictions.

        Args:
            device_id: Device or model identifier
            **kwargs: Additional parameters (e.g., sensor_key, limit)

        Returns:
            DataFrame with latest data
        """
        pass

    @abstractmethod
    def train(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        Train the model on provided data.

        Args:
            data: Training data
            **kwargs: Additional training parameters

        Returns:
            Dictionary with training results and metrics
        """
        pass

    @abstractmethod
    def predict(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        Make predictions using the trained model.

        Args:
            data: Input data for predictions
            **kwargs: Additional prediction parameters

        Returns:
            Dictionary with predictions and metadata
        """
        pass

    def add_algorithm(self, key: str, algorithm: BaseAlgorithm) -> None:
        """
        Add an algorithm to this model.

        Args:
            key: Identifier for the algorithm
            algorithm: Algorithm instance
        """
        self.algorithms[key] = algorithm

    def get_algorithm(self, key: str) -> Optional[BaseAlgorithm]:
        """
        Get an algorithm by key.

        Args:
            key: Algorithm identifier

        Returns:
            Algorithm instance or None if not found
        """
        return self.algorithms.get(key)

    def list_algorithms(self) -> List[str]:
        """
        Get list of algorithm keys.

        Returns:
            List of algorithm identifiers
        """
        return list(self.algorithms.keys())

    def save(self, path: Path) -> None:
        """
        Save the model and all its algorithms.

        Args:
            path: Directory path where to save the model
        """
        import joblib

        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save model metadata
        metadata = {
            "name": self.name,
            "is_trained": self.is_trained,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "algorithm_keys": list(self.algorithms.keys()),
        }
        joblib.dump(metadata, path / "metadata.pkl")

        # Save each algorithm
        for key, algorithm in self.algorithms.items():
            algorithm.save(path / f"algorithm_{key}.pkl")

    def load(self, path: Path) -> None:
        """
        Load the model and all its algorithms.

        Args:
            path: Directory path where the model is saved
        """
        import joblib

        path = Path(path)

        # Load metadata
        metadata = joblib.load(path / "metadata.pkl")
        self.name = metadata["name"]
        self.is_trained = metadata["is_trained"]
        self.created_at = metadata["created_at"]
        self.last_updated = metadata.get("last_updated")

        # Load algorithms
        for key in metadata["algorithm_keys"]:
            algorithm_path = path / f"algorithm_{key}.pkl"
            if key in self.algorithms:
                self.algorithms[key].load(algorithm_path)

    def get_info(self) -> Dict[str, Any]:
        """
        Get model information.

        Returns:
            Dictionary with model details
        """
        return {
            "name": self.name,
            "is_trained": self.is_trained,
            "created_at": self.created_at.isoformat(),
            "last_updated": (self.last_updated.isoformat() if self.last_updated else None),
            "algorithms": {
                key: {"type": algo.__class__.__name__, "is_trained": algo.is_trained}
                for key, algo in self.algorithms.items()
            },
        }

    def __repr__(self) -> str:
        status = "trained" if self.is_trained else "untrained"
        return f"{self.__class__.__name__}(name='{self.name}', algorithms={len(self.algorithms)}, status='{status}')"
