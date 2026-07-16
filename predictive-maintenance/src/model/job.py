import json
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd
from tb_ce_client.models import Alarm, AlarmSeverity, AlarmStatus, EntityId, EntityType, TenantId

from library import AnomalyPredictor, ForecastModel
from library.models.anomaly_predictor import feature_cols, load_models, predict_failure
from library.storage import ModelStorageService
from src.logger import logger
from src.model.client import get_client
from src.model.quarkus_client import get_quarkus_client
from src.settings import settings

from .shared import get_data_registry

MAX_LOG_ENTRIES = 1000
SYS_TENANT_ID = "13814000-1dd2-11b2-8080-808080808080"

JSONValue = Union[
    str,
    int,
    float,
    bool,
    None,
    dict[str, "JSONValue"],
    list["JSONValue"],
]


def to_native(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    return str(o)


def add_model_log(model_id: str, level: str, message: JSONValue) -> None:
    if level.lower() == "prediction":
        pass
    elif level.lower() == "error":
        logger.error(f"[{model_id}] {message}")
    elif level.lower() == "warn":
        logger.warning(f"[{model_id}] {message}")
    else:
        logger.info(f"[{model_id}] {message}")


def anomaly_predict_model(
    model_id: str,
    iteration: int,
    device_id: str,
    hourly_models: dict,
    data_registry,
):
    add_model_log(model_id, "info", f"Fetching latest data for device {device_id}")
    anomalyModel = AnomalyPredictor(data_registry=get_data_registry())
    (
        telemetry_df,
        failures_df,
        maintenance_df,
        machines_df,
        errors_df,
    ) = anomalyModel.fetch(
        device_id,
        start_date=datetime(2011, 1, 5, 2, 0, 0) - pd.Timedelta(hours=24),
    )
    if (
        telemetry_df.empty
        and errors_df.empty
        and maintenance_df.empty
        and failures_df.empty
        and machines_df.empty
    ):
        add_model_log(model_id, "warn", "No data available for prediction")
        return False
    add_model_log(model_id, "info", f"Fetched {len(telemetry_df)} rows of data")
    if telemetry_df.empty:
        add_model_log(model_id, "warn", "No data available for prediction")
        return False
    add_model_log(
        model_id,
        "info",
        f"Running prediction on data with columns: {list(telemetry_df.columns)}",
    )
    telemetry_df["datetime"] = pd.to_datetime(telemetry_df["datetime"])
    start_time = telemetry_df["datetime"].max()
    start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    predictions = predict_failure(
        start_time_str,
        {},
        telemetry_df,
        errors_df,
        maintenance_df,
        failures_df,
        machines_df,
        feature_cols,
        hourly_models,
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
    )
    hourly_records = list(predictions["hourly_predictions"].values())
    predictions_json_str = json.dumps(hourly_records, default=to_native)
    predictions_json = json.loads(predictions_json_str)
    for idx, prediction in enumerate(predictions_json):
        hours_to_add = idx + 1
        start_time_dt = (
            start_time.to_pydatetime() if hasattr(start_time, "to_pydatetime") else start_time
        )
        prediction["datetime"] = (start_time_dt + timedelta(hours=hours_to_add)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        add_model_log(
            model_id,
            "prediction",
            {
                "iteration": iteration,
                "device_id": device_id,
                "prediction_index": idx + 1,
                "total_predictions": len(predictions_json),
                "result": prediction,
            },
        )
        if prediction.get("failure_predicted", True):
            print(
                f"[PREDICTION JOB] {model_id} - Anomaly detected in prediction index {idx + 1}",
                flush=True,
            )
            confidence_score = prediction.get("general_failure_probability", 0.0)
            print(
                f"[PREDICTION JOB] {model_id} - "
                f"Anomaly detected with confidence score {confidence_score}",
                flush=True,
            )
            tenant_id = TenantId(id=uuid.UUID(SYS_TENANT_ID))
            alarm = get_client().save_alarm(
                Alarm(
                    tenant_id=tenant_id,
                    originator=EntityId(id=uuid.UUID(device_id), entity_type=EntityType.DEVICE),
                    type="Anomaly Detected",
                    acknowledged=False,
                    cleared=False,
                    name=f"Anomaly Detected - {model_id} "
                    f"- Iteration {iteration} - Prediction {idx + 1}",
                    status=AlarmStatus.ACTIVE_UNACK,
                    severity=AlarmSeverity.CRITICAL
                    if confidence_score > 0.8
                    else AlarmSeverity.MAJOR
                    if confidence_score > 0.5
                    else AlarmSeverity.MINOR,
                    details={
                        "model_id": model_id,
                        "iteration": iteration,
                        "prediction_index": idx + 1,
                        "total_predictions": len(predictions_json),
                        "confidence_score": confidence_score,
                        "prediction": prediction,
                    },
                )
            )
            print(
                f"[PREDICTION JOB] {model_id} - Alarm created: {alarm}",
                flush=True,
            )
        save_prediction(data_registry, model_id, prediction, "Anomaly")
    add_model_log(
        model_id,
        "info",
        f"Anomaly check completed (iteration {iteration}): sent {len(predictions_json)} predictions",
    )


def forecast_predict_model(
    model_id: str, iteration: int, device_id: str, model, data_registry
):
    add_model_log(model_id, "info", f"Starting forecast (iteration {iteration})")
    result = model.forecast(predict_for=24)
    result_copy = json.loads(json.dumps(result, default=to_native))
    sensor_count = 0

    prediction_summary = []
    for sensor_name, sensor_data in result_copy.items():
        if sensor_name != "forecast_max_steps" and isinstance(sensor_data, dict):
            sensor_count += 1
            forecast_values = sensor_data.get("forecast", [])
            timestamp_values = sensor_data.get("timestamp", [])
            summary = {
                "sensor": sensor_name,
                "forecast_count": len(forecast_values),
                "first_forecast": forecast_values[0] if forecast_values else None,
                "first_timestamp": timestamp_values[0] if timestamp_values else None,
            }
            prediction_summary.append(summary)

            add_model_log(
                model_id,
                "prediction",
                {
                    "iteration": iteration,
                    "device_id": device_id,
                    "sensor": sensor_name,
                    "result": sensor_data,
                    "prediction_type": "forecast",
                },
            )

            saved_prediction = {
                "sensor_name": sensor_name,
                "prediction_info": sensor_data.get(
                    "prediction_info", {"group_by_period_ms": None, "recent_point_ts": None}
                ),
                "forecast": sensor_data.get("forecast", [None])[0],
            }

            save_prediction(data_registry, model_id, saved_prediction, "Forecast")

            saved_prediction["prediction_type"] = "history"

            add_model_log(model_id, "prediction", saved_prediction)

    add_model_log(
        model_id,
        "info",
        f"Forecast completed (iteration {iteration}): {sensor_count} sensors - {prediction_summary}",
    )

    for sensor in model.sensors:
        if sensor in result and "timestamp" in result[sensor]:
            timestamps = result[sensor].get("timestamp", [])
            if timestamps:
                from datetime import datetime as dt

                min_ts = dt.fromtimestamp(timestamps[0] / 1000)
                max_ts = dt.fromtimestamp(timestamps[-1] / 1000)
                logger.info(
                    f"SAVE DEBUG - {sensor}: prediction timestamps [{min_ts} to {max_ts}], {len(timestamps)} points"
                )


class PredictionJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(
        self,
        model_id: str,
        model_type: str,
        device_id: str = None,
        group_by_ms_per_sensor: dict = None,
        aggregation_funcs: dict = None,
    ) -> bool:
        with self._lock:
            if model_id in self._jobs and self._jobs[model_id]["status"] == "running":
                add_model_log(model_id, "warn", "Job already running")
                return False

            job_thread = threading.Thread(
                target=self._worker,
                args=(
                    model_id,
                    model_type,
                    device_id,
                    group_by_ms_per_sensor,
                    aggregation_funcs,
                ),
                daemon=True,
            )
            self._jobs[model_id] = {
                "model_id": model_id,
                "model_type": model_type,
                "device_id": device_id,
                "status": "running",
                "paused": False,
                "start_time": datetime.now().isoformat() + "Z",
                "last_run": None,
                "iterations": 0,
                "thread": job_thread,
            }
            job_thread.start()

        add_model_log(model_id, "info", "Job started successfully")
        return True

    def stop(self, model_id: str) -> bool:
        with self._lock:
            if model_id not in self._jobs:
                return False
            self._jobs[model_id]["status"] = "stopped"
        add_model_log(model_id, "info", "Job stop requested")
        return True

    def pause(self, model_id: str) -> bool:
        with self._lock:
            if model_id not in self._jobs or self._jobs[model_id]["status"] != "running":
                return False
            self._jobs[model_id]["paused"] = True
        add_model_log(model_id, "info", "Job paused")
        return True

    def unpause(self, model_id: str) -> bool:
        with self._lock:
            if model_id not in self._jobs or self._jobs[model_id]["status"] != "running":
                return False
            self._jobs[model_id]["paused"] = False
        add_model_log(model_id, "info", "Job resumed")
        return True

    def _worker(
        self,
        model_id: str,
        model_type: str,
        device_id: str = None,
        group_by_ms_per_sensor: dict = None,
        aggregation_funcs: dict = None,
    ) -> None:
        add_model_log(model_id, "info", f"Prediction job started for {model_type}")
        data_registry = get_data_registry()
        try:
            add_model_log(model_id, "info", f"Initializing model worker for {model_type}")
            model_dir = Path(settings.models_path) / model_id
            add_model_log(model_id, "info", f"Model directory: {model_dir}")

            storage = ModelStorageService()
            if not any(model_dir.iterdir()) if model_dir.exists() else True:
                add_model_log(model_id, "info", "Local model dir empty, loading from storage backend...")
                try:
                    storage.load_model(model_id, model_dir)
                    add_model_log(model_id, "info", "Model loaded from storage backend")
                except FileNotFoundError:
                    add_model_log(model_id, "error", f"No model artifacts found for {model_id}")
                    return

            hourly_models = None
            model = None

            if model_type == "AnomalyPredictor":
                add_model_log(model_id, "info", "Getting data registry...")
                add_model_log(model_id, "info", f"Loading model from {model_dir}...")
                hourly_models = load_models(model_dir)
                add_model_log(model_id, "info", "Model loaded successfully from disk")
                interval = 24 * 60 * 60 * 60
            elif model_type == "ForecastModel":
                forecast_id = model_id.rsplit("/", 1)[0]
                model_config = data_registry.fetch_predictive_model_config(forecast_id)
                sensors = model_config.get("attributes", [])
                sensors = [sensor["key"] for sensor in sensors if "key" in sensor]
                device_id = device_id or model_config.get("device_id")
                model = ForecastModel(
                    sensors=sensors,
                    name=model_id,
                    algorithm_name="prophet",
                    lookback=20,
                    device_id=device_id,
                    data_registry=data_registry,
                    group_by_ms_per_sensor=group_by_ms_per_sensor,
                    aggregation_funcs=aggregation_funcs,
                )
                model.load(model_dir)
                interval = 5
            else:
                add_model_log(model_id, "error", f"Unknown model type: {model_type}")
                return

            add_model_log(
                model_id,
                "info",
                f"Model loaded successfully, running predictions every {interval}s",
            )
            iteration = 0
            while True:
                should_break = self._inner_loop(
                    model_id,
                    model_type,
                    device_id,
                    model,
                    hourly_models,
                    iteration,
                    data_registry,
                )
                if should_break:
                    break
                iteration += 1
                threading.Event().wait(interval)
        except Exception as e:
            add_model_log(model_id, "error", f"Job worker crashed: {str(e)}")
        finally:
            with self._lock:
                if model_id in self._jobs:
                    self._jobs[model_id]["status"] = "stopped"
            add_model_log(model_id, "info", "Job worker terminated")

    def _inner_loop(
        self,
        model_id: str,
        model_type: str,
        device_id: str,
        model,
        hourly_models: dict,
        iteration: int,
        data_registry,
    ) -> bool:
        with self._lock:
            if model_id not in self._jobs or self._jobs[model_id]["status"] != "running":
                add_model_log(model_id, "info", "Job stopped by user")
                return True

            if self._jobs[model_id].get("paused", False):
                threading.Event().wait(1)
                return False

            self._jobs[model_id]["iterations"] = iteration
            self._jobs[model_id]["last_run"] = datetime.now().isoformat() + "Z"

        try:
            add_model_log(model_id, "info", f"Running prediction iteration #{iteration}")

            if model_type == "AnomalyPredictor":
                anomaly_predict_model(
                    model_id, iteration, device_id, hourly_models, data_registry
                )
            elif model_type == "ForecastModel":
                forecast_predict_model(model_id, iteration, device_id, model, data_registry)
        except Exception as e:
            error_details = traceback.format_exc()
            add_model_log(model_id, "error", f"Prediction failed: {str(e)}")
            add_model_log(model_id, "error", f"Traceback: {error_details}")
        return False


def save_prediction(data_registry, model_id: str, message, source):
    """Save the prediction result to the database or any persistent storage"""
    _model_id = model_id.split("/")[0] if "/" in model_id else model_id
    created_at = datetime.now().isoformat() + "Z"
    created_time = int(time.time() * 1000)

    if isinstance(message, dict) and "timestamp" in message:
        timestamps = message.get("timestamp", [])
        if timestamps:
            from datetime import datetime as dt

            min_ts = dt.fromtimestamp(timestamps[0] / 1000)
            max_ts = dt.fromtimestamp(timestamps[-1] / 1000)
            logger.info(
                f"Saving {source} prediction: timestamps [{min_ts} to {max_ts}], {len(timestamps)} points"
            )

    max_retries = 5
    for attempt in range(max_retries):
        try:
            get_quarkus_client().create_anomaly_history_prediction(
                model_id=_model_id,
                prediction_type=source,
                body={
                    "createdAt": created_at,
                    "createdTime": created_time,
                    "predictionTime": created_at,
                    "predictionValue": message,
                },
            )
            return
        except Exception as e:
            if attempt < max_retries - 1:
                wait = min(2 ** attempt, 30)
                add_model_log(model_id, "warn",
                    f"Failed to save prediction (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {wait}s: {str(e)}")
                time.sleep(wait)
            else:
                error_details = traceback.format_exc()
                add_model_log(model_id, "error", f"Failed to save prediction after {max_retries} attempts: {str(e)}")
                add_model_log(model_id, "error", f"Save traceback: {error_details}")
