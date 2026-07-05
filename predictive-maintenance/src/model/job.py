import sys

sys.path.append("..")

import json
import threading
import time
import traceback
import uuid
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Set, Union

import numpy as np
import pandas as pd
from sqlalchemy import text
from tb_ce_client.models import Alarm, AlarmSeverity, AlarmStatus, EntityId, EntityType, TenantId

from library import AnomalyPredictor, ForecastModel
from library.models.anomaly_predictor import feature_cols, load_models, predict_failure
from src.logger import logger
from src.model.client import get_client
from src.model.utils import active_jobs, get_job_status, get_or_create_job_status, job_lock
from src.settings import settings

from .shared import get_data_registry

model_logs: Dict[str, deque] = {}
MAX_LOG_ENTRIES = 1000
SYS_TENANT_ID = "13814000-1dd2-11b2-8080-808080808080"

log_broadcasters: Dict[str, Set[Callable]] = {}
broadcaster_lock = threading.Lock()

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
    if model_id not in model_logs:
        model_logs[model_id] = deque(maxlen=MAX_LOG_ENTRIES)

    if "forecast" in model_id.lower():
        source = "ForecastModel"
    elif "anomaly" in model_id.lower():
        source = "AnomalyModel"
    else:
        source = "System"

    log_entry = {
        "timestamp": datetime.now().isoformat() + "Z",
        "level": level.upper(),
        "message": message,
        "type": (
            "forecast"
            if "forecast" in model_id
            else "anomaly"
            if "anomaly" in model_id
            else "system"
        ),
        "source": source,
    }
    model_logs[model_id].append(log_entry)

    if level.lower() == "prediction":
        pass
    elif level.lower() == "error":
        logger.error(f"[{model_id}] {message}")
    elif level.lower() == "warn":
        logger.warning(f"[{model_id}] {message}")
    else:
        logger.info(f"[{model_id}] {message}")

    with broadcaster_lock:
        if model_id in log_broadcasters:
            for broadcast_callback in log_broadcasters[model_id].copy():
                try:
                    broadcast_callback(log_entry)
                except Exception as e:
                    logger.error(f"Error broadcasting log to WebSocket: {str(e)}")


def prediction_job_worker(
    model_id: str,
    model_type: str,
    device_id: str = None,
    group_by_ms_per_sensor: dict = None,
    aggregation_funcs: dict = None,
):
    add_model_log(model_id, "info", f"Prediction job started for {model_type}")
    data_registry = get_data_registry()
    try:
        add_model_log(model_id, "info", f"Initializing model worker for {model_type}")
        path = settings.models_path
        model_dir = Path(path) / model_id
        add_model_log(model_id, "info", f"Model directory: {model_dir}")

        hourly_models = None
        model = None

        if model_type == "AnomalyPredictor":
            add_model_log(model_id, "info", "Getting data registry...")
            add_model_log(model_id, "info", f"Loading model from {model_dir}...")
            hourly_models = load_models(model_dir)
            add_model_log(model_id, "info", "Model loaded successfully from disk")
            interval = 24 * 60 * 60 * 60
        elif model_type == "ForecastModel":
            data_registry = get_data_registry()
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
            should_break = inner_loop(
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
        with job_lock:
            if model_id in active_jobs:
                active_jobs[model_id]["status"] = "stopped"
        add_model_log(model_id, "info", "Job worker terminated")


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


def inner_loop(
    model_id: str,
    model_type: str,
    device_id: str,
    model,
    hourly_models: dict,
    iteration: int,
    data_registry,
) -> bool:
    with job_lock:
        if model_id not in active_jobs or active_jobs[model_id]["status"] != "running":
            add_model_log(model_id, "info", "Job stopped by user")
            return True

        if active_jobs[model_id].get("paused", False):
            threading.Event().wait(1)
            return False
    result = {}
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
    _id = uuid.uuid4().hex
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

    try:
        with data_registry.engine.connect() as conn:
            query = text(
                """
                INSERT INTO tb_quarkus.predictions
                (model_id, created_at, created_time, prediction_time, prediction_type, prediction_value)
                VALUES (:model_id, :created_at, :created_time, :prediction_time, :prediction_type, :prediction_value)
                """
            )

            conn.execute(
                query,
                {
                    "model_id": _model_id,
                    "created_at": created_at,
                    "created_time": created_time,
                    "prediction_time": created_at,
                    "prediction_type": source,
                    "prediction_value": json.dumps(message, default=to_native),
                },
            )
            conn.commit()
    except Exception as e:
        error_details = traceback.format_exc()
        add_model_log(model_id, "error", f"Failed to save prediction: {str(e)}")
        add_model_log(model_id, "error", f"Save traceback: {error_details}")


def start_prediction_job(
    model_id: str,
    model_type: str,
    device_id: str = None,
    group_by_ms_per_sensor: dict = None,
    aggregation_funcs: dict = None,
) -> bool:
    with job_lock:
        if model_id in active_jobs and active_jobs[model_id]["status"] == "running":
            add_model_log(model_id, "warn", "Job already running")
            return False

        job_thread = threading.Thread(
            target=prediction_job_worker,
            args=(model_id, model_type, device_id, group_by_ms_per_sensor, aggregation_funcs),
            daemon=True,
        )

        active_jobs[model_id] = {
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
        add_model_log(model_id, "info", f"Job started successfully")
        return True


def stop_prediction_job(model_id: str) -> bool:
    with job_lock:
        if model_id not in active_jobs:
            return False

        active_jobs[model_id]["status"] = "stopped"
        add_model_log(model_id, "info", "Job stop requested")
        return True


def pause_prediction_job(model_id: str) -> bool:
    with job_lock:
        if model_id not in active_jobs:
            return False

        if active_jobs[model_id]["status"] != "running":
            return False

        active_jobs[model_id]["paused"] = True
        add_model_log(model_id, "info", "Job paused")
        return True


def unpause_prediction_job(model_id: str) -> bool:
    with job_lock:
        if model_id not in active_jobs:
            return False

        if active_jobs[model_id]["status"] != "running":
            return False

        active_jobs[model_id]["paused"] = False
        add_model_log(model_id, "info", "Job resumed")
        return True


def get_model_logs(model_id: str, level: str = "all", limit: int = 100) -> list:
    if model_id not in model_logs:
        return []

    logs = list(model_logs[model_id])
    if level.upper() != "ALL":
        logs = [log for log in logs if log["level"] == level.upper()]

    logs = logs[-limit:]

    return logs


def subscribe_to_logs(model_id: str, callback: Callable) -> None:
    with broadcaster_lock:
        if model_id not in log_broadcasters:
            log_broadcasters[model_id] = set()
        log_broadcasters[model_id].add(callback)
        logger.info(f"WebSocket subscribed to logs for {model_id}")


def unsubscribe_from_logs(model_id: str, callback: Callable) -> None:
    with broadcaster_lock:
        if model_id in log_broadcasters:
            log_broadcasters[model_id].discard(callback)
            if not log_broadcasters[model_id]:
                del log_broadcasters[model_id]
            logger.info(f"WebSocket unsubscribed from logs for {model_id}")


def subscribe_to_job_status(model_id: str, callback: Callable, rand_id: int) -> None:
    logger.info(f"Subscribing to job status for {model_id}", extra={"rand_id": rand_id})
    job = get_or_create_job_status(model_id, rand_id)
    logger.info(f"Got job status for {model_id}: {job}", extra={"rand_id": rand_id})
    with job["read_lock"]:
        logger.info(
            f"Inside read_lock for subscribing to job status for {model_id}",
            extra={"rand_id": rand_id},
        )
        _len = len(job.get("job_status_subscribers", set()))
        logger.info(
            f"Acquired read_lock for subscribing to job status for {model_id}",
            extra={"rand_id": rand_id},
        )
        if "job_status_subscribers" not in job:
            logger.info(
                f"Initializing job_status_subscribers set for {model_id}",
                extra={"rand_id": rand_id},
            )
            job["job_status_subscribers"] = set()
        logger.info(
            f"Adding subscriber callback for job status for {model_id}",
            extra={"rand_id": rand_id},
        )
        job["job_status_subscribers"].add(callback)
        logger.info(
            f"WebSocket subscribed to job status for {model_id}", extra={"rand_id": rand_id}
        )
        subscribers_len = len(job["job_status_subscribers"])
        logger.info(
            f"Total job status subscribers for {model_id} ({_len} before): {subscribers_len}",
            extra={"rand_id": rand_id},
        )


def unsubscribe_from_job_status(model_id: str, callback: Callable) -> None:
    job = get_job_status(model_id)
    if job:
        with job["read_lock"]:
            if "job_status_subscribers" in job:
                job["job_status_subscribers"].discard(callback)
                if not job["job_status_subscribers"]:
                    del job["job_status_subscribers"]
                logger.info(f"WebSocket unsubscribed from job status for {model_id}")


def notify_job_status_update(model_id: str) -> None:
    logger.info(f"Notifying job status update for {model_id}")
    job = get_job_status(model_id)
    logger.info(f"Job status for {model_id}: {job}")
    if job:
        subscribers = job["job_status_subscribers"].copy()
        logger.info(f"Notifying {len(subscribers)} subscribers for job status of {model_id}")
        for callback in subscribers:
            try:
                logger.info(f"Notifying subscriber {callback} for job status of {model_id}")
                callback(job)
            except Exception as e:
                logger.error(f"Error notifying job status subscriber: {str(e)}")
