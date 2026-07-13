from datetime import datetime
from typing import Any, Callable

from src.logger import logger
from src.model.job import PredictionJobManager
from src.model.shared import get_data_registry, train_and_save_model

ProgressCallback = Callable[[str, dict[str, Any]], None]


def activate_forecast(
    forecast_id: str,
    *,
    job_manager: PredictionJobManager,
    device_id: str | None = None,
    model_type: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    target = (model_type or "BOTH").upper()

    data_registry = get_data_registry()
    model_config = data_registry.fetch_predictive_model_config(forecast_id)
    device_id = device_id or model_config["device_id"]

    sensors = [sensor["key"] for sensor in model_config.get("attributes", []) if "key" in sensor]
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

    if target in {"BOTH", "FORECAST"}:
        forecast_model_id = f"{forecast_id}/forecast_model"
        _progress(
            progress_callback,
            forecast_model_id,
            20,
            "training_forecast",
            "Training ForecastModel...",
        )
        train_and_save_model(
            model_id=forecast_model_id,
            model_type="ForecastModel",
            device_id=device_id,
            data_registry=data_registry,
            sensors=sensors,
            lookback=20,
            group_by_ms=default_group_by_ms,
            group_by_ms_per_sensor=group_by_ms_per_sensor,
            aggregation_funcs=aggregation_funcs,
            progress_callback=lambda progress: _progress_dict(
                progress_callback, forecast_model_id, progress
            ),
        )
        _progress(
            progress_callback,
            forecast_model_id,
            50,
            "forecast_complete",
            "ForecastModel trained successfully",
        )
        job_manager.start(
            forecast_model_id,
            "ForecastModel",
            device_id,
            group_by_ms_per_sensor=group_by_ms_per_sensor,
            aggregation_funcs=aggregation_funcs,
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
        train_and_save_model(
            model_id=anomaly_model_id,
            model_type="AnomalyPredictor",
            device_id=device_id,
            data_registry=data_registry,
            sensors=sensors,
            train_start_date=model_config.get("anomaly_start_date", datetime(2014, 1, 1)),
            train_end_date=model_config.get("anomaly_end_date", datetime(2016, 1, 1)),
            progress_callback=lambda progress: _progress_dict(
                progress_callback, anomaly_model_id, progress
            ),
        )
        _progress(
            progress_callback,
            anomaly_model_id,
            95,
            "anomaly_complete",
            "AnomalyPredictor trained successfully",
        )
        job_manager.start(anomaly_model_id, "AnomalyPredictor", device_id)

    logger.info(f"Kafka worker activation complete for forecastId={forecast_id}")


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
