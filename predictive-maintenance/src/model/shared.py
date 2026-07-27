"""
Shared utilities and constants for model services
"""

import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

from library import AnomalyPredictor, ForecastModel
from library.core.data_registry import DataRegistry
from library.models.anomaly_predictor import save_models, train_model
import library.storage as storage
from src.logger import logger
from src.settings import settings


class TrainingError(Exception):
    """Raised when model training fails with a user-actionable reason."""

    def __init__(self, message: str, code: str = "TRAINING_FAILED", cause: Exception | None = None):
        super().__init__(message)
        self.code = code
        self.cause = cause


def get_data_registry() -> DataRegistry:
    return DataRegistry(
        telemetry_keys=settings.telemetry_keys,
        error_keys=settings.error_keys,
        component_keys=settings.component_keys,
    )


# const names
RANDOM_FOREST = "random_forest"
PROPHET = "prophet"
LSTM = "lstm"
XGBOOST = "xgboost"
ANOMALY_PREDICTOR = "AnomalyPredictor"
FORECAST_MODEL = "ForecastModel"

MODEL_TYPE_MAP = {
    ANOMALY_PREDICTOR: [
        {"model_name": RANDOM_FOREST, "model_parameters": {}},
        {"model_name": XGBOOST, "model_parameters": {}},
    ],
    FORECAST_MODEL: [
        {"model_name": LSTM, "model_parameters": {}},
        {"model_name": XGBOOST, "model_parameters": {}},
    ],
}

MODEL_TYPE_MAP_CLASS = {
    ANOMALY_PREDICTOR: {
        "model_name": AnomalyPredictor,
        "default_algorithm": MODEL_TYPE_MAP[ANOMALY_PREDICTOR][0]["model_name"],
        "default_hyperparams": MODEL_TYPE_MAP[ANOMALY_PREDICTOR][0]["model_parameters"],
    },
    FORECAST_MODEL: {
        "model_name": ForecastModel,
        "default_algorithm": MODEL_TYPE_MAP[FORECAST_MODEL][0]["model_name"],
        "default_hyperparams": MODEL_TYPE_MAP[FORECAST_MODEL][0]["model_parameters"],
    },
}

def update_training_progress(model_id: str, progress: dict | None, rand_id: str = None):
    logger.info(
        f"{rand_id} - Updating training progress for model_id={model_id}: {progress}",
        extra={"rand_id": rand_id},
    )


def train_and_save_model(
    model_id: str,
    model_type: str,
    device_id: str | None = None,
    algorithm: str | None = None,
    hyperparams: dict | None = None,
    data_registry: DataRegistry | None = None,
    sensors: list | None = None,
    group_by_ms_per_sensor: dict | None = None,
    aggregation_funcs: dict | None = None,
    epochs_per_sensor: dict | None = None,
    progress_callback=None,
    **kwargs,
) -> dict:
    ModelClass, default_algorithm, default_hyperparams = (
        MODEL_TYPE_MAP_CLASS[model_type]["model_name"],
        MODEL_TYPE_MAP_CLASS[model_type]["default_algorithm"],
        MODEL_TYPE_MAP_CLASS[model_type]["default_hyperparams"],
    )

    algorithm = algorithm or default_algorithm
    hyperparams = hyperparams or default_hyperparams
    device_id = device_id or model_id

    if data_registry is None:
        data_registry = get_data_registry()

    path = settings.models_path
    model_dir = Path(path) / model_id
    model_dir.mkdir(parents=True, exist_ok=True)

    rand_id = os.urandom(4).hex()

    if model_type == "AnomalyPredictor":
        train_start_date = kwargs.get(
            "train_start_date",
            datetime.now() - pd.Timedelta(days=365 * 2),
        )
        train_end_date = kwargs.get("train_end_date", datetime.now())

        discovered = data_registry.discover_device_keys(device_id)
        component_keys = discovered["root_causes"] or discovered["parts_replaced"]
        error_keys = discovered["error_codes"]

        if not component_keys:
            raise TrainingError(
                f"No component keys found for device {device_id}. "
                "Add failure or maintenance records (root causes / parts replaced) "
                "to the database before training the anomaly model.",
                code="NO_COMPONENT_KEYS",
            )
        if not error_keys:
            raise TrainingError(
                f"No error keys found for device {device_id}. "
                "Add error records to the database before training the anomaly model.",
                code="NO_ERROR_KEYS",
            )
        if not sensors:
            raise TrainingError(
                f"No telemetry keys provided for device {device_id}. "
                "Add telemetry data to ThingsBoard before training.",
                code="NO_TELEMETRY_KEYS",
            )

        model = ModelClass(
            name=model_id,
            algorithm_name=algorithm,
            algorithm_hyperparams=hyperparams,
            data_registry=data_registry,
            device_id=device_id,
            additional_info=kwargs,
            sensors=sensors,
            error_keys=error_keys,
            component_keys=component_keys,
            train_start_date=train_start_date,
            train_end_date=train_end_date,
        )

        update_training_progress(
            model_id,
            {
                "step": "fetching_data",
                "message": f"Fetching training data from {model.train_start_date} to {model.train_end_date}...",
                "progress": 20,
            },
        )
        if progress_callback:
            progress_callback(
                {
                    "step": "fetching_data",
                    "message": f"Fetching training data from {model.train_start_date} to {model.train_end_date}...",
                    "progress": 20,
                }
            )

        print(
            f"[TRAIN] Fetching data for device_id={device_id} starting from {model.train_start_date} to {model.train_end_date}",
            flush=True,
        )
        telemetry_df, failures_df, maintenance_df, machines_df, errors_df = model.fetch(
            device_id=device_id,
            start_date=model.train_start_date,
            end_date=model.train_end_date,
            **kwargs,
        )
        print(f"[TRAIN] Data fetched. Training model...", flush=True)
        if failures_df.empty:
            raise TrainingError(
                f"No failure records found for device {device_id}. "
                "To train the anomaly model, add failure/maintenance records to the device "
                "in ThingsBoard first (via the Failure Mode tab or API).",
                code="NO_FAILURE_DATA",
            )

        update_training_progress(
            model_id,
            {"step": "training", "message": "Training AnomalyPredictor model...", "progress": 40},
        )
        if progress_callback:
            progress_callback(
                {
                    "step": "training",
                    "message": "Training AnomalyPredictor model...",
                    "progress": 40,
                }
            )

        print(f"[TRAIN] Training AnomalyPredictor model for device_id={device_id}...", flush=True)

        hourly_models, feature_cols, labeled_features_clean = train_model(
            telemetry_df,
            errors_df,
            maintenance_df,
            failures_df,
            machines_df,
            components=component_keys,
            error_classes=error_keys,
            sensors=sensors,
            algorithm="random_forest",
        )

        if not hourly_models:
            raise TrainingError(
                "Training produced no models. The data may not contain enough variation "
                "to learn failure patterns. Check that failure records span different time periods.",
                code="EMPTY_TRAINING_OUTPUT",
            )

        # Update progress: saving
        update_training_progress(
            model_id, {"step": "saving", "message": "Saving trained model...", "progress": 80}
        )
        if progress_callback:
            progress_callback(
                {"step": "saving", "message": "Saving trained model...", "progress": 80}
            )

        print(f"[TRAIN] Model trained. Saving models...", flush=True)
        try:
            save_models(hourly_models, model_dir)
        except Exception as save_err:
            raise TrainingError(
                f"Model trained successfully but failed to save to disk ({model_dir}). "
                f"Check disk space and permissions. Error: {save_err}",
                code="MODEL_SAVE_FAILED",
                cause=save_err,
            ) from save_err
        try:
            storage.save_model(model_id, model_dir)
            print(f"[TRAIN] Models synced to model-store", flush=True)
            shutil.rmtree(model_dir, ignore_errors=True)
            print(f"[TRAIN] Local model cache cleared: {model_dir}", flush=True)
        except Exception as sync_err:
            print(f"[TRAIN] Model-store sync failed (local save OK): {sync_err}", flush=True)
    elif model_type == "ForecastModel":
        logger.info(
            f"{rand_id} - Starting training for ForecastModel with model_id={model_id}",
            extra={"rand_id": rand_id},
        )
        update_training_progress(
            model_id,
            {"step": "initializing", "message": "Initializing ForecastModel...", "progress": 20},
            rand_id=rand_id,
        )
        if progress_callback:
            progress_callback(
                {"step": "initializing", "message": "Initializing ForecastModel...", "progress": 20}
            )

        logger.info(
            f"{rand_id} - Initializing ForecastModel instance for model_id={model_id}",
            extra={"rand_id": rand_id},
        )

        model = ModelClass(
            name=model_id,
            algorithm_name=algorithm,
            algorithm_hyperparams=hyperparams,
            data_registry=data_registry,
            device_id=device_id,
            additional_info=kwargs,
            sensors=sensors,
            group_by_ms_per_sensor=group_by_ms_per_sensor,
            aggregation_funcs=aggregation_funcs,
            epochs_per_sensor=epochs_per_sensor,
        )
        logger.info(
            f"{rand_id} - ForecastModel instance initialized for model_id={model_id}",
            extra={"rand_id": rand_id},
        )

        update_training_progress(
            model_id,
            {"step": "training", "message": "Training ForecastModel...", "progress": 50},
            rand_id=rand_id,
        )
        logger.info(
            f"{rand_id} - Updated progress to training for model_id={model_id}",
            extra={"rand_id": rand_id},
        )
        if progress_callback:
            progress_callback(
                {"step": "training", "message": "Training ForecastModel...", "progress": 50}
            )

        model.train(progress_callback=progress_callback)

        logger.info(
            f"{rand_id} - ForecastModel trained for model_id={model_id}", extra={"rand_id": rand_id}
        )
        update_training_progress(
            model_id,
            {"step": "saving", "message": "Saving trained model...", "progress": 80},
            rand_id=rand_id,
        )
        if progress_callback:
            progress_callback(
                {"step": "saving", "message": "Saving trained model...", "progress": 80}
            )

        try:
            model.save(model_dir)
        except Exception as save_err:
            raise TrainingError(
                f"Forecast model trained successfully but failed to save to disk ({model_dir}). "
                f"Check disk space and permissions. Error: {save_err}",
                code="MODEL_SAVE_FAILED",
                cause=save_err,
            ) from save_err
        try:
            storage.save_model(model_id, model_dir)
            logger.info(
                f"{rand_id} - ForecastModel synced to model-store for model_id={model_id}",
                extra={"rand_id": rand_id},
            )
            shutil.rmtree(model_dir, ignore_errors=True)
            logger.info(
                f"{rand_id} - Local model cache cleared: {model_dir}",
                extra={"rand_id": rand_id},
            )
        except Exception as sync_err:
            logger.warning(
                f"{rand_id} - Model-store sync failed (local save OK): {sync_err}",
                extra={"rand_id": rand_id},
            )

    update_training_progress(model_id, None, rand_id=rand_id)

    return {
        "status": "success",
        "model_id": model_id,
        "model_type": model_type,
        "model_path": str(model_dir),
        "training_results": {},
    }
