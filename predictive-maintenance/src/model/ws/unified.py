import asyncio
from datetime import datetime
from typing import Callable, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.logger import logger
from src.model.job import (
    pause_prediction_job,
    stop_prediction_job,
    subscribe_to_logs,
    unpause_prediction_job,
    unsubscribe_from_job_status,
    unsubscribe_from_logs,
)
from src.model.predictive_model import (
    unsubscribe_from_model_status,
)
from src.model.utils import get_job_status

from .func.handle_activate import handle_activate
from .func.handle_job_logs import handle_job_logs
from .func.handle_job_status import handle_job_status
from .func.handle_model_status import handle_model_status

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
