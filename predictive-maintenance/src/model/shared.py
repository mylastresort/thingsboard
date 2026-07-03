"""
Shared utilities and constants for model services
"""

import os
import threading
from datetime import datetime
from pathlib import Path

import pandas as pd

from library import AnomalyPredictor, ForecastModel
from library.core.data_registry import DataRegistry
from library.models.anomaly_predictor import save_models, train_model
from src.logger import logger
from src.model.utils import active_jobs, get_job_status, get_or_create_job_status, job_lock
from src.settings import settings


def get_data_registry() -> DataRegistry:
    database_url = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/thingsboard"
    )

    return DataRegistry(
        database_url=database_url,
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

training_results = None


def _update_training_progress_impl(model_id: str, progress: dict, rand_id: str = None):
    """
    Internal implementation of update_training_progress that runs in a thread.

    Args:
        model_id: The model ID
        progress: Dictionary with progress information (step, message, progress percentage)
        rand_id: Random ID for tracking
    """

    logger.info(
        f"{rand_id} - Updating training progress for model_id={model_id}: {progress}",
        extra={"rand_id": rand_id},
    )
    job = get_job_status(model_id)
    logger.info(
        f"{rand_id} - Retrieved job for model_id={model_id}: {job}",
        extra={"rand_id": rand_id},
    )
    if job is not None:
        with job["read_lock"]:
            logger.info(
                f"{rand_id} - Acquired read_lock for model_id={model_id}",
                extra={"rand_id": rand_id},
            )
            job["training_progress"] = progress

    # Notify subscribers after updating
    from src.model.job import notify_job_status_update

    notify_job_status_update(model_id)


def update_training_progress(model_id: str, progress: dict, rand_id: str = None):
    """
    Update the training progress for a model in active_jobs and notify subscribers.
    This is non-blocking - runs in a background thread.

    Args:
        model_id: The model ID
        progress: Dictionary with progress information (step, message, progress percentage)
        rand_id: Random ID for tracking
    """
    thread = threading.Thread(
        target=_update_training_progress_impl, args=(model_id, progress, rand_id), daemon=True
    )
    thread.start()


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

    logger.info(
        f"{rand_id} - Creating active job entry for model_id={model_id} if not exists",
        extra={"rand_id": rand_id},
    )
    get_or_create_job_status(
        model_id,
        {
            "model_id": model_id,
            "model_type": model_type,
            "device_id": device_id,
            "status": "training",
            "paused": False,
            "start_time": datetime.now().isoformat() + "Z",
            "last_run": None,
            "iterations": 0,
            "training_progress": None,
            "thread": None,
        },
        rand_id=rand_id,
    )

    if model_type == "AnomalyPredictor":
        train_start_date = kwargs.get(
            "train_start_date",
            datetime.now() - pd.Timedelta(days=365 * 2),
        )
        train_end_date = kwargs.get("train_end_date", datetime.now())
        model = ModelClass(
            name=model_id,
            algorithm_name=algorithm,
            algorithm_hyperparams=hyperparams,
            data_registry=data_registry,
            device_id=device_id,
            additional_info=kwargs,
            sensors=sensors,
            # group_by_ms_per_sensor=group_by_ms_per_sensor,
            # aggregation_funcs=aggregation_funcs,
            train_start_date=train_start_date,
            train_end_date=train_end_date,
        )

        # Update progress: fetching data
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
            return {
                "status": "failed",
                "reason": "No failure data found",
                "model_id": model_id,
                "model_type": model_type,
            }

        # Update progress: training
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
            components=[
                "comp1",
                "comp2",
                "comp3",
                "comp4",
            ],
            error_classes=[
                "error1",
                "error2",
                "error3",
                "error4",
                "error5",
            ],
            # algorithm=algorithm,
            algorithm="random_forest",
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
        save_models(hourly_models, model_dir)
    elif model_type == "ForecastModel":
        logger.info(
            f"{rand_id} - Starting training for ForecastModel with model_id={model_id}",
            extra={"rand_id": rand_id},
        )
        # Update progress: initializing
        logger.info(
            f"{rand_id} - Updating progress to initializing for model_id={model_id}",
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

        # Initialize model with data registry
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
        )
        logger.info(
            f"{rand_id} - ForecastModel instance initialized for model_id={model_id}",
            extra={"rand_id": rand_id},
        )

        # Update progress: training
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

        model.train()

        logger.info(
            f"{rand_id} - ForecastModel trained for model_id={model_id}", extra={"rand_id": rand_id}
        )
        # Update progress: saving
        update_training_progress(
            model_id,
            {"step": "saving", "message": "Saving trained model...", "progress": 80},
            rand_id=rand_id,
        )
        if progress_callback:
            progress_callback(
                {"step": "saving", "message": "Saving trained model...", "progress": 80}
            )

        model.save(model_dir)

    # Clear training progress and remove training status when complete
    update_training_progress(model_id, None, rand_id=rand_id)

    logger.info(
        f"{rand_id} - Removing active job entry for model_id={model_id} after training completion",
        extra={"rand_id": rand_id},
    )
    with job_lock:
        if model_id in active_jobs and active_jobs[model_id]["status"] == "training":
            # Remove the job entry since training is done (will be recreated by start_prediction_job)
            del active_jobs[model_id]

    return {
        "status": "success",
        "model_id": model_id,
        "model_type": model_type,
        "model_path": str(model_dir),
        "training_results": {},
    }
