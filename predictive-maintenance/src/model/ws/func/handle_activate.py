import asyncio
import os
import traceback
from datetime import datetime

from fastapi import WebSocket

from src.logger import logger
from src.model.job import start_prediction_job
from src.model.predictive_model import (
    ModelStatus,
    get_or_create_predictive_model,
)
from src.model.shared import get_data_registry, train_and_save_model


async def handle_activate(websocket: WebSocket, command_id: int, forecast_id: str, data: dict):
    rand_id = os.urandom(4).hex()

    logger.info(
        f"Handling activate command for forecastId={forecast_id}", extra={"rand_id": rand_id}
    )

    predictive_model = get_or_create_predictive_model(forecast_id)

    predictive_model.set_status(ModelStatus.PENDING)
    logger.info(
        f"PredictiveModel status set to PENDING for forecastId={forecast_id}",
        extra={"rand_id": rand_id},
    )
    predictive_model.update_training_progress(0, "initializing", "Starting activation...")
    logger.info(
        f"PredictiveModel training progress initialized for forecastId={forecast_id}",
        extra={"rand_id": rand_id},
    )

    try:
        logger.info(
            f"Starting activation process for forecastId={forecast_id}",
            extra={"rand_id": rand_id},
        )

        predictive_model.update_training_progress(
            5, "initializing", "Initializing data registry..."
        )

        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "progress",
                "step": "initializing",
                "message": "Initializing data registry...",
                "progress": 5,
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )

        logger.info(
            f"Data registry initialization started for forecastId={forecast_id}",
            extra={"rand_id": rand_id},
        )

        data_registry = await asyncio.to_thread(get_data_registry)

        logger.info(
            f"Data registry initialized for forecastId={forecast_id}", extra={"rand_id": rand_id}
        )

        device_id = data.get("deviceId")

        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "progress",
                "step": "fetching_config",
                "message": "Fetching device configuration...",
                "progress": 10,
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )

        logger.info(
            f"Fetching device configuration for forecastId={forecast_id}",
            extra={"rand_id": rand_id},
        )

        try:
            model_config = data_registry.fetch_predictive_model_config(forecast_id)
            device_id = model_config["device_id"]

            predictive_model.device_id = device_id
            predictive_model.update_training_progress(
                10, "fetching_config", "Configuration fetched"
            )

            logger.info(
                f"Device ID fetched for forecastId={forecast_id}: {device_id}",
                extra={"rand_id": rand_id},
            )
        except Exception as e:
            logger.error(f"Failed to fetch model configuration: {str(e)}")
            traceback.print_exc()

            predictive_model.set_status(
                ModelStatus.ERROR, f"Failed to fetch configuration: {str(e)}"
            )

            await websocket.send_json(
                {
                    "commandId": command_id,
                    "type": "error",
                    "message": f"Failed to fetch configuration: {str(e)}",
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )
            return

        try:
            sensors = model_config.get("attributes", [])
            sensors = [sensor["key"] for sensor in sensors if "key" in sensor]

            aggregation_funcs = {
                sensor["key"]: sensor.get("aggregation", "average")
                for sensor in model_config.get("attributes", [])
                if "key" in sensor
            }

            default_group_by_ms = model_config.get("forecast_grouping_ms", 5000)
            group_by_ms_per_sensor = {}
            for sensor in model_config.get("attributes", []):
                if "key" in sensor:
                    sensor_key = sensor["key"]
                    sensor_group_by_ms = (
                        sensor.get("groupByMs")
                        if sensor.get("groupByMs") is not None
                        else sensor.get("grouping_interval_ms", default_group_by_ms)
                    )
                    group_by_ms_per_sensor[sensor_key] = sensor_group_by_ms

            group_by_ms = default_group_by_ms

            logger.info(
                (
                    f"Starting ForecastModel training for forecastId={forecast_id} "
                    f"with sensors={sensors}, group_by_ms={group_by_ms}, "
                    f"group_by_ms_per_sensor={group_by_ms_per_sensor}, "
                    f"aggregation_funcs={aggregation_funcs}"
                ),
                extra={"rand_id": rand_id},
            )

            predictive_model.update_training_progress(
                20, "training_forecast", "Training ForecastModel..."
            )
            predictive_model.set_sub_model_status("forecast_model", "training")

            forecast_result = await asyncio.to_thread(
                train_and_save_model,
                model_id=f"{forecast_id}/forecast_model",
                model_type="ForecastModel",
                device_id=device_id,
                data_registry=data_registry,
                sensors=sensors,
                lookback=20,
                group_by_ms=group_by_ms,
                group_by_ms_per_sensor=group_by_ms_per_sensor,
                aggregation_funcs=aggregation_funcs,
            )
            predictive_model.set_sub_model_status("forecast_model", "trained", trained=True)
            predictive_model.update_training_progress(
                50, "forecast_complete", "ForecastModel trained successfully"
            )

            await websocket.send_json(
                {
                    "commandId": command_id,
                    "type": "progress",
                    "step": "forecast_complete",
                    "message": "ForecastModel trained successfully",
                    "progress": 50,
                    "metrics": forecast_result.get("training_results", {}),
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )
        except Exception as e:
            logger.error(f"ForecastModel training failed: {str(e)}")

            predictive_model.set_sub_model_status("forecast_model", "error")
            predictive_model.set_status(
                ModelStatus.ERROR, f"ForecastModel training failed: {str(e)}"
            )

            await websocket.send_json(
                {
                    "commandId": command_id,
                    "type": "error",
                    "step": "forecast_failed",
                    "message": f"ForecastModel training failed: {str(e)}",
                    "progress": 50,
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )
            return

        try:
            logger.info(
                f"Starting AnomalyPredictor training for forecastId={forecast_id}",
                extra={"rand_id": rand_id},
            )

            predictive_model.update_training_progress(
                55, "training_anomaly", "Training AnomalyPredictor..."
            )
            predictive_model.set_sub_model_status("anomaly_predictor", "training")

            await websocket.send_json(
                {
                    "commandId": command_id,
                    "type": "progress",
                    "step": "training_anomaly",
                    "message": "Training AnomalyPredictor model...",
                    "progress": 55,
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )

            anomaly_result = await asyncio.to_thread(
                train_and_save_model,
                model_id=f"{forecast_id}/anomaly_predictor",
                model_type="AnomalyPredictor",
                device_id=device_id,
                data_registry=data_registry,
                sensors=sensors,
                train_start_date=model_config.get("anomaly_start_date", datetime(2014, 1, 1)),
                train_end_date=model_config.get("anomaly_end_date", datetime(2016, 1, 1)),
            )

            predictive_model.set_sub_model_status("anomaly_predictor", "trained", trained=True)
            predictive_model.update_training_progress(
                95, "anomaly_complete", "AnomalyPredictor trained successfully"
            )

            await websocket.send_json(
                {
                    "commandId": command_id,
                    "type": "progress",
                    "step": "anomaly_complete",
                    "message": "AnomalyPredictor trained successfully",
                    "progress": 95,
                    "metrics": anomaly_result.get("training_results", {}),
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )
        except Exception as e:
            logger.error(f"AnomalyPredictor training failed: {str(e)}")

            predictive_model.set_sub_model_status("anomaly_predictor", "error")
            predictive_model.set_status(
                ModelStatus.ERROR, f"AnomalyPredictor training failed: {str(e)}"
            )

            await websocket.send_json(
                {
                    "commandId": command_id,
                    "type": "error",
                    "step": "anomaly_failed",
                    "message": f"AnomalyPredictor training failed: {str(e)}",
                    "progress": 95,
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )
            return

        predictive_model.set_status(ModelStatus.ACTIVE)
        predictive_model.update_training_progress(100, "complete", "Model activation complete")

        logger.info(f"[ACTIVATE] Starting AnomalyPredictor prediction job for {forecast_id}")
        await asyncio.to_thread(
            start_prediction_job,
            f"{forecast_id}/anomaly_predictor",
            "AnomalyPredictor",
            device_id,
        )
        logger.info("[ACTIVATE] AnomalyPredictor prediction job started")

        logger.info(f"[ACTIVATE] Starting ForecastModel prediction job for {forecast_id}")
        job_started = await asyncio.to_thread(
            start_prediction_job,
            f"{forecast_id}/forecast_model",
            "ForecastModel",
            device_id,
            group_by_ms_per_sensor=group_by_ms_per_sensor,
            aggregation_funcs=aggregation_funcs,
        )
        logger.info(f"[ACTIVATE] ForecastModel prediction job start result: {job_started}")

        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "complete",
                "message": "Model activation complete",
                "forecastId": forecast_id,
                "progress": 100,
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )

    except Exception as e:
        logger.error(f"Error in activate handler: {str(e)}", exc_info=True)

        predictive_model.set_status(ModelStatus.ERROR, str(e))

        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )
