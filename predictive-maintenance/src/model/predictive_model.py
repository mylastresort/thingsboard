"""
PredictiveModel class to manage overall model status for predictive maintenance forecasts.
Tracks the lifecycle status of a predictive model: inactive -> pending -> active
"""

import threading
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Optional, Set

from src.logger import logger


class ModelStatus(str, Enum):
    """Status of a predictive model"""

    INACTIVE = "inactive"  # Model hasn't been trained yet
    PENDING = "pending"  # Model is training
    ACTIVE = "active"  # Model has been trained successfully
    ERROR = "error"  # Model training failed


# Global registry of predictive models: {forecast_id: PredictiveModel}
_predictive_models: Dict[str, "PredictiveModel"] = {}
_models_lock = threading.Lock()


class PredictiveModel:
    """
    Manages the overall status of a predictive maintenance model.

    This class tracks:
    - The overall model status (inactive, pending, active, error)
    - Associated sub-models (forecast_model, anomaly_predictor)
    - Status subscribers for real-time updates
    """

    def __init__(self, forecast_id: str, device_id: Optional[str] = None):
        self.forecast_id = forecast_id
        self.device_id = device_id
        self.status = ModelStatus.INACTIVE
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.training_started_at: Optional[datetime] = None
        self.training_completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.training_progress: int = 0
        self.training_step: Optional[str] = None
        self.training_message: Optional[str] = None

        # Track sub-model statuses
        self.sub_models: Dict[str, dict] = {
            "forecast_model": {"status": "inactive", "trained": False},
            "anomaly_predictor": {"status": "inactive", "trained": False},
        }

        # Thread safety
        self._lock = threading.Lock()

        # Status subscribers for real-time updates
        self._status_subscribers: Set[Callable] = set()

        logger.info(f"PredictiveModel created for forecast_id={forecast_id}")

    def set_status(self, status: ModelStatus, message: Optional[str] = None) -> None:
        """Update the model status and notify subscribers"""
        with self._lock:
            old_status = self.status
            self.status = status
            self.updated_at = datetime.now()

            if status == ModelStatus.PENDING:
                self.training_started_at = datetime.now()
            elif status == ModelStatus.ACTIVE:
                self.training_completed_at = datetime.now()
            elif status == ModelStatus.ERROR:
                self.error_message = message

            logger.info(
                f"PredictiveModel status changed for {self.forecast_id}: {old_status} -> {status}"
            )

        # Notify subscribers outside the lock
        self._notify_subscribers()

    def update_training_progress(
        self, progress: int, step: Optional[str] = None, message: Optional[str] = None
    ) -> None:
        """Update training progress and notify subscribers"""
        with self._lock:
            self.training_progress = progress
            self.training_step = step
            self.training_message = message
            self.updated_at = datetime.now()

        logger.info(
            f"Training progress updated for {self.forecast_id}: "
            f"{progress}%, step={step}, message={message}"
        )
        logger.info(f"Notifying subscribers for {self.forecast_id} after progress update")
        self._notify_subscribers()

    def set_sub_model_status(
        self, sub_model: str, status: str, trained: Optional[bool] = None
    ) -> None:
        """Update a sub-model's status"""
        with self._lock:
            if sub_model in self.sub_models:
                self.sub_models[sub_model]["status"] = status
                if trained is not None:
                    self.sub_models[sub_model]["trained"] = trained
                self.updated_at = datetime.now()

        self._notify_subscribers()

    def subscribe(self, callback: Callable) -> None:
        """Subscribe to status updates"""
        with self._lock:
            self._status_subscribers.add(callback)
            logger.info(
                f"Subscriber added for {self.forecast_id}, "
                f"total subscribers: {len(self._status_subscribers)}"
            )

    def unsubscribe(self, callback: Callable) -> None:
        """Unsubscribe from status updates"""
        with self._lock:
            self._status_subscribers.discard(callback)
            logger.info(f"Subscriber removed for {self.forecast_id}")

    def _notify_subscribers(self) -> None:
        """Notify all subscribers of status change"""
        logger.info(f"Notifying subscribers for {self.forecast_id}")
        with self._lock:
            subscribers = self._status_subscribers.copy()
            status_data = self._to_dict_unlocked()

        logger.info(f"Notifying {len(subscribers)} subscribers for {self.forecast_id}")

        for callback in subscribers:
            try:
                callback(status_data)
            except Exception as e:
                logger.error(f"Error notifying subscriber for {self.forecast_id}: {str(e)}")

    def _to_dict_unlocked(self) -> dict:
        """Convert to dictionary - must be called while holding self._lock"""
        return {
            "forecastId": self.forecast_id,
            "deviceId": self.device_id,
            "status": self.status.value,
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() + "Z" if self.updated_at else None,
            "trainingStartedAt": (
                self.training_started_at.isoformat() + "Z" if self.training_started_at else None
            ),
            "trainingCompletedAt": (
                self.training_completed_at.isoformat() + "Z" if self.training_completed_at else None
            ),
            "errorMessage": self.error_message,
            "trainingProgress": self.training_progress,
            "trainingStep": self.training_step,
            "trainingMessage": self.training_message,
            "subModels": self.sub_models.copy(),
        }

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        with self._lock:
            return self._to_dict_unlocked()


# Registry functions


def get_predictive_model(forecast_id: str) -> Optional[PredictiveModel]:
    """Get a predictive model by forecast_id"""
    with _models_lock:
        return _predictive_models.get(forecast_id)


def get_or_create_predictive_model(
    forecast_id: str, device_id: Optional[str] = None
) -> PredictiveModel:
    """Get or create a predictive model"""
    with _models_lock:
        if forecast_id not in _predictive_models:
            _predictive_models[forecast_id] = PredictiveModel(forecast_id, device_id)
        elif device_id and not _predictive_models[forecast_id].device_id:
            _predictive_models[forecast_id].device_id = device_id
        return _predictive_models[forecast_id]


def remove_predictive_model(forecast_id: str) -> bool:
    """Remove a predictive model from the registry"""
    with _models_lock:
        if forecast_id in _predictive_models:
            del _predictive_models[forecast_id]
            logger.info(f"PredictiveModel removed for {forecast_id}")
            return True
        return False


def get_all_predictive_models() -> Dict[str, PredictiveModel]:
    """Get all predictive models"""
    with _models_lock:
        return _predictive_models.copy()


def subscribe_to_model_status(
    forecast_id: str, callback: Callable, create_if_missing: bool = True
) -> Optional[PredictiveModel]:
    """
    Subscribe to a predictive model's status updates.

    Args:
        forecast_id: The forecast ID
        callback: Function to call when status changes
        create_if_missing: If True, create the model if it doesn't exist

    Returns:
        The PredictiveModel instance, or None if not found and create_if_missing is False
    """
    if create_if_missing:
        model = get_or_create_predictive_model(forecast_id)
    else:
        model = get_predictive_model(forecast_id)

    if model:
        model.subscribe(callback)

    return model


def unsubscribe_from_model_status(forecast_id: str, callback: Callable) -> bool:
    """
    Unsubscribe from a predictive model's status updates.

    Returns:
        True if successfully unsubscribed, False if model not found
    """
    model = get_predictive_model(forecast_id)
    if model:
        model.unsubscribe(callback)
        return True
    return False


def get_model_status(forecast_id: str) -> Optional[dict]:
    """
    Get the current status of a predictive model as a dictionary.

    Returns:
        Status dict or None if model not found
    """
    model = get_predictive_model(forecast_id)
    if model:
        return model.to_dict()
    return None


def set_model_status(
    forecast_id: str,
    status: ModelStatus,
    message: Optional[str] = None,
    device_id: Optional[str] = None,
) -> PredictiveModel:
    """
    Set the status of a predictive model (creates if doesn't exist).

    Returns:
        The PredictiveModel instance
    """
    model = get_or_create_predictive_model(forecast_id, device_id)
    model.set_status(status, message)
    return model
