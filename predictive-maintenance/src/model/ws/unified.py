"""
Unified WebSocket endpoint: /ws/unified
Handles model activation (training), prediction listening, and log subscription
Uses ThingsBoard command pattern with commandId
"""

import asyncio
import json
import os
import traceback
from datetime import datetime
from random import randint
from typing import Callable, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.logger import logger
from src.model.job import (
    get_model_logs,
    pause_prediction_job,
    start_prediction_job,
    stop_prediction_job,
    subscribe_to_job_status,
    subscribe_to_logs,
    unpause_prediction_job,
    unsubscribe_from_job_status,
    unsubscribe_from_logs,
)
from src.model.predictive_model import (
    ModelStatus,
    get_or_create_predictive_model,
    unsubscribe_from_model_status,
)
from src.model.shared import get_data_registry, train_and_save_model
from src.model.utils import get_job_status

router = APIRouter()


@router.websocket("/ws/unified")
async def unified_model_stream(websocket: WebSocket):
    await websocket.accept()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Unauthorized - no token")
        return

    async def send_response(data: dict):
        """Send a response without blocking the message loop"""
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error(f"Error sending response: {str(e)}")

    def send_response_bg(data: dict):
        """Fire-and-forget send as background task"""
        create_logged_task(send_response(data), "send_response")

    def create_logged_task(coro, name: str = "unnamed"):
        """Create a background task with exception logging"""
        task = asyncio.create_task(coro)

        def handle_task_exception(t):
            try:
                exc = t.exception()
                if exc:
                    logger.error(f"Background task '{name}' failed: {exc}")
            except asyncio.CancelledError:
                logger.debug(f"Background task '{name}' was cancelled")

        task.add_done_callback(handle_task_exception)
        return task

    prediction_subscriptions: Dict[str, Set[str]] = {}  # {forecastId: {modelTypes}}
    log_subscriptions: Set[str] = set()  # {forecastIds}
    log_callbacks: Dict[str, Callable] = {}  # {model_id: callback_function}
    job_status_callbacks: Dict[str, Callable] = {}  # {model_id: callback_function}
    model_status_callbacks: Dict[str, Callable] = {}  # {forecast_id: callback_function}
    last_iterations: Dict[str, int] = {}  # {model_id: last_iteration}

    try:
        await websocket.send_json(
            {
                "type": "connection",
                "message": "Connected to unified model service",
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )

        while True:
            message = await websocket.receive_json()

            command_id = message.get("commandId") or message.get(
                "cmdId"
            )  # Accept either commandId or cmdId for compatibility
            msg_type = message.get("type")
            forecast_id = message.get("forecastId")
            data = message.get("data", {})

            # Validate commandId (except for connection/ping messages from Java backend)
            if command_id is None and msg_type not in ["connection", "ping"]:
                send_response_bg(
                    {
                        "type": "error",
                        "message": "Missing required field: commandId",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            # Handle ping
            if msg_type == "ping":
                send_response_bg(
                    {
                        "commandId": command_id,
                        "type": "pong",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            # Validate forecastId for other types (except connection/ping)
            if not forecast_id and msg_type not in ["ping", "connection"]:
                send_response_bg(
                    {
                        "commandId": command_id,
                        "type": "error",
                        "message": "Missing required field: forecastId",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            try:
                assert command_id is not None
            except AssertionError:
                logger.error(f"Missing commandId in message: {message}")
                send_response_bg(
                    {
                        "type": "error",
                        "message": "Missing required field: commandId",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            # Handle activate command - run as background task so message loop continues
            if msg_type == "activate":
                logger.info(f"Received activate command for forecastId={forecast_id}")
                create_logged_task(
                    handle_activate(websocket, int(command_id), forecast_id, data),
                    "handle_activate",
                )
                continue

            # Handle job_status command - run as background task
            if msg_type == "job_status":
                create_logged_task(
                    handle_job_status(websocket, command_id, forecast_id), "handle_job_status"
                )
                continue

            if msg_type == "model_status":
                logger.info(
                    "[MODEL_STATUS] Received model_status command for "
                    f"forecastId={forecast_id}, commandId={command_id}"
                )
                create_logged_task(
                    handle_model_status(websocket, command_id, forecast_id, model_status_callbacks),
                    "handle_model_status",
                )
                continue

            if msg_type == "unsubscribe_model_status":
                if forecast_id in model_status_callbacks:
                    callback = model_status_callbacks[forecast_id]
                    unsubscribe_from_model_status(forecast_id, callback)
                    del model_status_callbacks[forecast_id]
                    logger.info(f"Unsubscribed from model status for {forecast_id}")

                send_response_bg(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "message": f"Unsubscribed from model status for {forecast_id}",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            if msg_type == "job_logs":
                create_logged_task(
                    handle_job_logs(websocket, command_id, forecast_id, data), "handle_job_logs"
                )
                continue

            if msg_type == "subscribe_predictions" or msg_type == "job_listen":
                model_type = (
                    message.get("modelType")
                    if msg_type == "job_listen"
                    else data.get("modelType", "anomaly")
                )

                if forecast_id not in prediction_subscriptions:
                    prediction_subscriptions[forecast_id] = set()

                prediction_subscriptions[forecast_id].add(model_type)

                model_id = (
                    f"{forecast_id}/{model_type}_predictor"
                    if model_type == "anomaly"
                    else f"{forecast_id}/forecast_model"
                )
                job_status = get_job_status(model_id)
                if job_status:
                    last_iterations[model_id] = job_status.get("iterations", 0)

                send_response_bg(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "model": model_type,
                        "forecastId": forecast_id,
                        "data": {
                            "status": "listening",
                            "message": (
                                f"Now listening to {model_type} predictions for {forecast_id}"
                            ),
                            "current_iteration": (
                                job_status.get("iterations", 0) if job_status else 0
                            ),
                        },
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            if msg_type == "unsubscribe_predictions":
                model_type = data.get("modelType", "anomaly")

                if forecast_id in prediction_subscriptions:
                    prediction_subscriptions[forecast_id].discard(model_type)
                    if not prediction_subscriptions[forecast_id]:
                        del prediction_subscriptions[forecast_id]

                send_response_bg(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "message": f"Unsubscribed from {model_type} predictions for {forecast_id}",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            if msg_type == "subscribe_logs":
                log_subscriptions.add(forecast_id)

                def create_log_callback(ws, fid, cmd_id, loop):
                    def log_callback(log_entry):
                        """Callback to send log immediately when it's created (thread-safe)"""
                        try:
                            # Schedule coroutine in the event loop from another thread
                            asyncio.run_coroutine_threadsafe(
                                ws.send_json(
                                    {
                                        "commandId": cmd_id,
                                        "type": "logs",
                                        "forecastId": fid,
                                        "data": {
                                            "logs": [
                                                {
                                                    "timestamp": log_entry["timestamp"],
                                                    "level": log_entry["level"],
                                                    "message": log_entry["message"],
                                                    "type": log_entry["type"],
                                                }
                                            ]
                                        },
                                        "timestamp": datetime.now().isoformat() + "Z",
                                    }
                                ),
                                loop,
                            )
                        except Exception as e:
                            logger.error(f"Error sending real-time log: {str(e)}")

                    return log_callback

                anomaly_model_id = f"{forecast_id}/anomaly_predictor"

                callback = create_log_callback(
                    websocket, forecast_id, command_id, asyncio.get_running_loop()
                )
                log_callbacks[anomaly_model_id] = callback
                subscribe_to_logs(anomaly_model_id, callback)

                forecast_model_id = f"{forecast_id}/forecast_model"

                callback = create_log_callback(
                    websocket, forecast_id, command_id, asyncio.get_running_loop()
                )
                log_callbacks[forecast_model_id] = callback
                subscribe_to_logs(forecast_model_id, callback)

                send_response_bg(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "message": f"Subscribed to real-time logs for {forecast_id}",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            if msg_type == "unsubscribe_logs":
                log_subscriptions.discard(forecast_id)
                model_id = f"{forecast_id}/anomaly_predictor"

                if model_id in log_callbacks:
                    unsubscribe_from_logs(model_id, log_callbacks[model_id])
                    del log_callbacks[model_id]

                model_id = f"{forecast_id}/forecast_model"

                if model_id in log_callbacks:
                    unsubscribe_from_logs(model_id, log_callbacks[model_id])
                    del log_callbacks[model_id]

                send_response_bg(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "message": f"Unsubscribed from logs for {forecast_id}",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            if msg_type == "stop_job":
                model_type = data.get("modelType", "both")
                success_list = []

                if model_type in ["anomaly", "both"]:
                    anomaly_model_id = f"{forecast_id}/anomaly_predictor"
                    success = stop_prediction_job(anomaly_model_id)
                    if success:
                        success_list.append("anomaly")

                if model_type in ["forecast", "both"]:
                    forecast_model_id = f"{forecast_id}/forecast_model"
                    success = stop_prediction_job(forecast_model_id)
                    if success:
                        success_list.append("forecast")

                send_response_bg(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "message": (
                            f"Job(s) stopped: {', '.join(success_list)}"
                            if success_list
                            else f"No active jobs found for {forecast_id}"
                        ),
                        "success": len(success_list) > 0,
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            if msg_type == "pause_job":
                model_type = data.get("modelType", "forecast")

                if model_type == "anomaly":
                    model_id = f"{forecast_id}/anomaly_predictor"
                else:
                    model_id = f"{forecast_id}/forecast_model"

                success = pause_prediction_job(model_id)

                send_response_bg(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "message": (
                            f"{model_type} job paused for {forecast_id}"
                            if success
                            else f"Could not pause {model_type} job for {forecast_id}"
                        ),
                        "success": success,
                        "forecastId": forecast_id,
                        "modelType": model_type,
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            if msg_type == "unpause_job":
                model_type = data.get("modelType", "forecast")

                if model_type == "anomaly":
                    model_id = f"{forecast_id}/anomaly_predictor"
                else:
                    model_id = f"{forecast_id}/forecast_model"

                success = unpause_prediction_job(model_id)

                send_response_bg(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "message": (
                            f"{model_type} job resumed for {forecast_id}"
                            if success
                            else f"Could not resume {model_type} job for {forecast_id}"
                        ),
                        "success": success,
                        "forecastId": forecast_id,
                        "modelType": model_type,
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            if msg_type == "connection":
                logger.info("Received connection message from Java backend")
                continue

            send_response_bg(
                {
                    "commandId": command_id,
                    "type": "error",
                    "message": f"Unknown command type: {msg_type}",
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )

    except WebSocketDisconnect as e:
        logger.info("Unified WebSocket client disconnected")
        logger.info("stacktrace:")
        logger.info(e)
    except Exception as e:
        logger.error(f"Error in unified WebSocket: {str(e)}", exc_info=True)
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )
        except Exception as send_error:
            logger.error(f"Error sending error message to client: {str(send_error)}")
            pass
    finally:
        for model_id, callback in log_callbacks.items():
            try:
                unsubscribe_from_logs(model_id, callback)
            except Exception as e:
                logger.error(f"Error unsubscribing from logs on cleanup: {str(e)}")

        for model_id, callback in job_status_callbacks.items():
            try:
                unsubscribe_from_job_status(model_id, callback)
            except Exception as e:
                logger.error(f"Error unsubscribing from job status on cleanup: {str(e)}")

        for forecast_id, callback in model_status_callbacks.items():
            try:
                unsubscribe_from_model_status(forecast_id, callback)
            except Exception as e:
                logger.error(f"Error unsubscribing from model status on cleanup: {str(e)}")

        logger.info("Unified WebSocket connection closed")


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


async def handle_job_status(
    websocket: WebSocket,
    command_id: int,
    forecast_id: str,
):
    """Handle job status request and subscribe to future updates"""
    try:
        rand_id = randint(100000, 999999)

        def create_status_callback(ws, fid, cmd_id, loop, model_type_str):
            logger.info(
                f"Creating job status callback for {fid} - {model_type_str}",
                extra={"rand_id": rand_id},
            )

            def status_callback(status_data):
                logger.info(
                    f"Job status callback triggered for {fid} - {model_type_str}: {status_data}",
                    extra={"rand_id": rand_id},
                )
                try:
                    serializable_data = json.loads(json.dumps(status_data, default=str))
                    logger.info(
                        f"Job status update for {fid} - {model_type_str}: {serializable_data}",
                        extra={"rand_id": rand_id},
                    )
                    future = asyncio.run_coroutine_threadsafe(
                        ws.send_json(
                            {
                                "commandId": cmd_id,
                                "type": "response",
                                "model": "job",
                                "model_type": model_type_str,
                                "data": serializable_data,
                                "forecastId": fid,
                                "timestamp": datetime.now().isoformat() + "Z",
                            }
                        ),
                        loop,
                    )

                    def log_job_result(f):
                        try:
                            f.result()
                            logger.debug(
                                "Successfully sent real-time status update for "
                                f"{fid} - {model_type_str}"
                            )
                        except Exception as send_error:
                            logger.error(
                                (
                                    f"Failed to send real-time status update for {fid} - "
                                    f"{model_type_str}: {str(send_error)}"
                                )
                            )

                    future.add_done_callback(log_job_result)
                except Exception as e:
                    logger.error(
                        f"Error preparing real-time status update: {str(e)}",
                        extra={"rand_id": rand_id},
                    )
                    import traceback

                    logger.error(f"Traceback: {traceback.format_exc()}")

            return status_callback

        model_id = f"{forecast_id}/anomaly_predictor"
        job_status_anomaly = get_job_status(model_id)
        job_status_anomaly = json.loads(json.dumps(job_status_anomaly, default=str))
        logger.info(
            f"Fetched job status for {model_id}: {job_status_anomaly}", extra={"rand_id": rand_id}
        )

        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "response",
                "model": "job",
                "model_type": "anomaly",
                "data": job_status_anomaly,
                "forecastId": forecast_id,
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )

        callback = create_status_callback(
            websocket, forecast_id, command_id, asyncio.get_running_loop(), "anomaly"
        )
        subscribe_to_job_status(model_id, callback, rand_id=rand_id)

        model_id = f"{forecast_id}/forecast_model"
        job_status_forecast = get_job_status(model_id)
        job_status_forecast = json.loads(json.dumps(job_status_forecast, default=str))
        logger.info(
            f"Fetched job status for {model_id}: {job_status_forecast}", extra={"rand_id": rand_id}
        )
        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "response",
                "model": "job",
                "model_type": "forecast",
                "data": job_status_forecast,
                "forecastId": forecast_id,
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )

        logger.info(f"Subscribing to job status updates for {model_id}", extra={"rand_id": rand_id})

        callback = create_status_callback(
            websocket, forecast_id, command_id, asyncio.get_running_loop(), "forecast"
        )
        logger.info(f"Storing job status callback for {model_id}", extra={"rand_id": rand_id})
        logger.info(f"Calling subscribe_to_job_status for {model_id}", extra={"rand_id": rand_id})
        subscribe_to_job_status(model_id, callback, rand_id=rand_id)
        logger.info(f"Subscribed to job status updates for {model_id}", extra={"rand_id": rand_id})

    except Exception as e:
        logger.error(f"Error in job status handler: {str(e)}", exc_info=True)
        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )


async def handle_model_status(
    websocket: WebSocket,
    command_id: int,
    forecast_id: str,
    model_status_callbacks: Dict[str, Callable],
):
    """
    Handle model status request for the overall predictive model.
    Returns the current status (inactive, pending, active, error) and subscribes to updates.
    """
    logger.info(
        (
            f"[MODEL_STATUS] ENTER handle_model_status: "
            f"forecast_id={forecast_id}, command_id={command_id}"
        )
    )
    try:
        rand_id = randint(100000, 999999)
        logger.info(f"[MODEL_STATUS] Step 1: Generated rand_id={rand_id}")

        logger.info(
            (
                "[MODEL_STATUS] Step 2: Checking existing callbacks, "
                f"keys={list(model_status_callbacks.keys())}"
            )
        )
        if forecast_id in model_status_callbacks:
            old_callback = model_status_callbacks[forecast_id]
            logger.info(f"[MODEL_STATUS] Step 2a: Unsubscribing old callback for {forecast_id}")
            unsubscribe_from_model_status(forecast_id, old_callback)
            del model_status_callbacks[forecast_id]
            logger.info("[MODEL_STATUS] Step 2b: Old callback removed")
        else:
            logger.info(f"[MODEL_STATUS] Step 2a: No existing callback for {forecast_id}")

        logger.info(f"[MODEL_STATUS] Step 3: Getting/creating predictive model for {forecast_id}")
        model = get_or_create_predictive_model(forecast_id)
        logger.info(f"[MODEL_STATUS] Step 3a: Got model, status={model.status}")
        model_status = model.to_dict()
        logger.info(
            (
                "[MODEL_STATUS] Step 3b: Model dict created, "
                f"status={model_status.get('status')}, "
                f"progress={model_status.get('trainingProgress')}"
            )
        )

        logger.info(f"[MODEL_STATUS] Step 4: Sending response to websocket, commandId={command_id}")
        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "response",
                "model": "predictive_model",
                "data": model_status,
                "forecastId": forecast_id,
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )
        logger.info("[MODEL_STATUS] Step 4a: Response sent successfully")

        logger.info("[MODEL_STATUS] Step 5: Creating callback for future updates")

        def create_model_status_callback(ws, fid, cmd_id, loop):
            def model_status_callback(status_data):
                """Callback for predictive model status updates.

                Fire and forget to avoid deadlock.
                """
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        ws.send_json(
                            {
                                "commandId": cmd_id,
                                "type": "response",
                                "model": "predictive_model",
                                "data": status_data,
                                "forecastId": fid,
                                "timestamp": datetime.now().isoformat() + "Z",
                            }
                        ),
                        loop,
                    )

                    def log_result(f):
                        try:
                            f.result()
                            logger.debug(
                                f"Successfully sent predictive model status update for {fid}"
                            )
                        except Exception as send_error:
                            logger.error(
                                (
                                    f"Failed to send predictive model status update for {fid}: "
                                    f"{str(send_error)}"
                                )
                            )

                    future.add_done_callback(log_result)
                except Exception as e:
                    logger.error(f"Error in model status callback: {str(e)}")

            return model_status_callback

        callback = create_model_status_callback(
            websocket, forecast_id, command_id, asyncio.get_running_loop()
        )
        logger.info("[MODEL_STATUS] Step 5a: Callback created")

        model.subscribe(callback)
        logger.info(
            "[MODEL_STATUS] Step 5b: Subscribed callback, total subscribers: "
            f"{len(model._status_subscribers)}"
        )

        model_status_callbacks[forecast_id] = callback
        logger.info(
            "[MODEL_STATUS] Step 6: Stored callback in model_status_callbacks, "
            f"keys now: {list(model_status_callbacks.keys())}"
        )

        logger.info(f"[MODEL_STATUS] EXIT handle_model_status: success for {forecast_id}")

    except Exception as e:
        logger.error(f"[MODEL_STATUS] ERROR in handle_model_status: {str(e)}", exc_info=True)
        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )


async def handle_job_logs(
    websocket: WebSocket,
    command_id: int,
    forecast_id: str,
    data: dict,
    source: str = "forecast_model",
):
    """Handle job logs request"""
    try:
        limit = data.get("limit", 100)
        model_id = f"{forecast_id}/" + source
        logs = get_model_logs(model_id, "all", limit)

        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "logs",
                "forecastId": forecast_id,
                "data": {"logs": logs, "count": len(logs)},
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )
    except Exception as e:
        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )
