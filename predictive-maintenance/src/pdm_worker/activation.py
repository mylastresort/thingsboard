import traceback
from datetime import datetime, timezone
from typing import Any, Callable

from src.logger import logger
from src.model.job import PredictionJobManager
from src.model.shared import TrainingError, get_data_registry, train_and_save_model

ProgressCallback = Callable[[str, dict[str, Any]], None]


def activate_forecast(
    forecast_id: str,
    *,
    job_manager: PredictionJobManager,
    device_id: str | None = None,
    model_type: str | None = None,
    progress_callback: ProgressCallback | None = None,
    sensor_key: str | None = None,
) -> None:
    target = (model_type or "BOTH").upper()

    data_registry = get_data_registry()
    model_config = data_registry.fetch_predictive_model_config(forecast_id)
    device_id = device_id or model_config["device_id"]

    all_sensors = [sensor["key"] for sensor in model_config.get("attributes", []) if "key" in sensor]
    aggregation_funcs = {
        sensor["key"]: sensor.get("aggregation", "average")
        for sensor in model_config.get("attributes", [])
        if "key" in sensor
    }
    default_group_by_ms = model_config.get("forecast_grouping_ms", 5000)
    group_by_ms_per_sensor = {
        sensor["key"]: (
            sensor.get("groupByMs")
            if sensor.get("groupByMs") is not None
            else sensor.get("grouping_interval_ms", default_group_by_ms)
        )
        for sensor in model_config.get("attributes", [])
        if "key" in sensor
    }
    epochs_per_sensor = {
        sensor["key"]: sensor.get("epochs", 1)
        for sensor in model_config.get("attributes", [])
        if "key" in sensor
    }

    if target in {"BOTH", "FORECAST"}:
        sensors = [sensor_key] if sensor_key else all_sensors
        forecast_model_id = (
            f"{forecast_id}/forecast_model/{sensor_key}"
            if sensor_key
            else f"{forecast_id}/forecast_model"
        )
        _progress(
            progress_callback,
            forecast_model_id,
            20,
            "training_forecast",
            f"Training ForecastModel for sensor {sensor_key or 'all'}...",
        )
        try:
            train_and_save_model(
                model_id=forecast_model_id,
                model_type="ForecastModel",
                device_id=device_id,
                data_registry=data_registry,
                sensors=sensors,
                lookback=20,
                group_by_ms=default_group_by_ms,
                group_by_ms_per_sensor={k: v for k, v in group_by_ms_per_sensor.items() if k in sensors},
                aggregation_funcs={k: v for k, v in aggregation_funcs.items() if k in sensors},
                epochs_per_sensor={k: v for k, v in epochs_per_sensor.items() if k in sensors},
                progress_callback=lambda progress: _progress_dict(
                    progress_callback, forecast_model_id, progress
                ),
            )
        except TrainingError as exc:
            _emit_failure(progress_callback, forecast_model_id, exc)
            if target == "FORECAST":
                raise
            logger.warning(
                "ForecastModel training failed (%s), continuing with AnomalyPredictor",
                exc.code,
            )
        except Exception as exc:
            code = "FORECAST_TRAINING_ERROR"
            _emit_failure(progress_callback, forecast_model_id, TrainingError(
                f"ForecastModel training failed unexpectedly: {exc}",
                code=code,
            ))
            if target == "FORECAST":
                raise
            logger.warning("ForecastModel training failed, continuing with AnomalyPredictor")
        else:
            _progress(
                progress_callback,
                forecast_model_id,
                50,
                "forecast_complete",
                f"ForecastModel trained successfully for sensor {sensor_key or 'all'}",
            )
            job_manager.start(
                forecast_model_id,
                "ForecastModel",
                device_id,
                group_by_ms_per_sensor={k: v for k, v in group_by_ms_per_sensor.items() if k in sensors},
                aggregation_funcs={k: v for k, v in aggregation_funcs.items() if k in sensors},
            )

    if target in {"BOTH", "ANOMALY"}:
        anomaly_model_id = f"{forecast_id}/anomaly_predictor"
        _progress(
            progress_callback,
            anomaly_model_id,
            55,
            "training_anomaly",
            "Training AnomalyPredictor...",
        )
        try:
            train_and_save_model(
                model_id=anomaly_model_id,
                model_type="AnomalyPredictor",
                device_id=device_id,
                data_registry=data_registry,
                sensors=all_sensors,
                train_start_date=_resolve_date(model_config, "anomalyStartDate", default=datetime(2014, 1, 1)),
                train_end_date=_resolve_date(model_config, "anomalyEndDate", default=datetime.now()),
                progress_callback=lambda progress: _progress_dict(
                    progress_callback, anomaly_model_id, progress
                ),
            )
        except TrainingError as exc:
            _emit_failure(progress_callback, anomaly_model_id, exc)
            if target == "ANOMALY":
                raise
            logger.warning(
                "AnomalyPredictor training failed (%s), continuing",
                exc.code,
            )
        except Exception as exc:
            _emit_failure(progress_callback, anomaly_model_id, TrainingError(
                f"AnomalyPredictor training failed unexpectedly: {exc}",
                code="ANOMALY_TRAINING_ERROR",
            ))
            if target == "ANOMALY":
                raise
            logger.warning("AnomalyPredictor training failed, continuing")
        else:
            _progress(
                progress_callback,
                anomaly_model_id,
                95,
                "anomaly_complete",
                "AnomalyPredictor trained successfully",
            )
            job_manager.start(anomaly_model_id, "AnomalyPredictor", device_id)

    logger.info(f"Kafka worker activation complete for forecastId={forecast_id} sensorKey={sensor_key}")


def _emit_failure(
    callback: ProgressCallback | None,
    model_id: str,
    exc: TrainingError,
) -> None:
    _progress_dict(callback, model_id, {
        "progress": 0,
        "step": "failed",
        "message": str(exc),
        "errorCode": exc.code,
        "status": "failed",
    })


def _progress(
    callback: ProgressCallback | None,
    model_id: str,
    percent: int,
    step: str,
    message: str,
) -> None:
    _progress_dict(callback, model_id, {"progress": percent, "step": step, "message": message})


def _progress_dict(
    callback: ProgressCallback | None,
    model_id: str,
    progress: dict[str, Any],
) -> None:
    if callback:
        callback(model_id, progress)


def _resolve_date(config: dict, key: str, default: datetime) -> datetime:
    value = config.get(key)
    if value is None:
        return default
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        if value == 0:
            return default
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return default
    return default
