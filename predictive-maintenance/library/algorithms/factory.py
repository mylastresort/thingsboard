"""
Algorithm factory - Registry for creating algorithm instances.
"""

from typing import Dict, Type

from ..core.algorithm_interface import BaseAlgorithm
from ..core.types import AlgorithmConfig
from .supervised import (
    RandomForestAdapter,
    XGBoostAdapter,
)
from .timeseries import XGBoostTimeSeriesAdapter


class AlgorithmRegistry:
    """
    Factory for creating algorithm instances.
    Uses registry pattern to allow dynamic algorithm registration.
    """

    _algorithms: Dict[str, Type[BaseAlgorithm]] = {}

    @classmethod
    def register(cls, name: str, algorithm_class: Type[BaseAlgorithm]) -> None:
        """
        Register an algorithm class.

        Args:
            name: Algorithm name/identifier
            algorithm_class: Algorithm class to register
        """
        cls._algorithms[name] = algorithm_class

    @classmethod
    def create(cls, config: AlgorithmConfig) -> BaseAlgorithm:
        """
        Create an algorithm instance from configuration.

        Args:
            config: Algorithm configuration

        Returns:
            Algorithm instance

        Raises:
            ValueError: If algorithm name is not registered
        """
        algorithm_class = cls._algorithms.get(config.name)
        if algorithm_class is None:
            raise ValueError(
                f"Algorithm '{config.name}' not found. "
                f"Available algorithms: {list(cls._algorithms.keys())}"
            )
        return algorithm_class(config)

    @classmethod
    def list_algorithms(cls) -> list[str]:
        """
        Get list of registered algorithm names.

        Returns:
            List of algorithm names
        """
        return list(cls._algorithms.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """
        Check if an algorithm is registered.

        Args:
            name: Algorithm name

        Returns:
            True if registered, False otherwise
        """
        return name in cls._algorithms


# Auto-register all algorithms
def _auto_register_algorithms():
    """Automatically register all algorithm implementations"""
    try:
        AlgorithmRegistry.register("random_forest", RandomForestAdapter)
        AlgorithmRegistry.register("xgboost", XGBoostAdapter)
    except ImportError:
        pass  # Supervised algorithms not yet implemented

    try:
        AlgorithmRegistry.register("xgboost_ts", XGBoostTimeSeriesAdapter)
    except ImportError:
        pass  # Time series algorithms not yet implemented


# Register algorithms on module import
_auto_register_algorithms()
