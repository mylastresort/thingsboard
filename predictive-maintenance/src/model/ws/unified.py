"""
Unified WebSocket endpoint: /ws/unified
Handles model activation (training), prediction listening, and log subscription
Uses ThingsBoard command pattern with commandId
"""

import asyncio
from datetime import datetime
from typing import Dict, Set, Callable
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.model.shared import get_data_registry, train_and_save_model
from src.model.job import (
    add_model_log,
    start_prediction_job,
    stop_prediction_job,
    pause_prediction_job,
    unpause_prediction_job,
    get_job_status,
    get_model_logs,
    subscribe_to_logs,
    unsubscribe_from_logs,
    subscribe_to_job_status,
    unsubscribe_from_job_status,
)
from src.settings import settings
from src.logger import logger  # Global logger
from pathlib import Path
import traceback

router = APIRouter()


@router.websocket("/ws/unified")
async def unified_model_stream(websocket: WebSocket):
    """
    Unified WebSocket endpoint for all model operations.

    Supports the following command types:

    1. activate - Train and activate models
    {
        "commandId": 123,
        "type": "activate",
        "forecastId": "uuid",
        "data": {
            "deviceId": "uuid"  // optional
        }
    }

    2. job_status - Get job status
    {
        "commandId": 124,
        "type": "job_status",
        "forecastId": "uuid"
    }

    3. job_logs - Get job logs
    {
        "commandId": 125,
        "type": "job_logs",
        "forecastId": "uuid",
        "data": {
            "limit": 100  // optional
        }
    }

    4. subscribe_predictions - Subscribe to real-time predictions
    {
        "commandId": 126,
        "type": "subscribe_predictions",
        "forecastId": "uuid",
        "data": {
            "modelType": "anomaly" | "forecast"
        }
    }

    5. unsubscribe_predictions - Unsubscribe from predictions
    {
        "commandId": 127,
        "type": "unsubscribe_predictions",
        "forecastId": "uuid",
        "data": {
            "modelType": "anomaly" | "forecast"
        }
    }

    6. subscribe_logs - Subscribe to real-time logs
    {
        "commandId": 128,
        "type": "subscribe_logs",
        "forecastId": "uuid"
    }

    7. unsubscribe_logs - Unsubscribe from logs
    {
        "commandId": 129,
        "type": "unsubscribe_logs",
        "forecastId": "uuid"
    }

    8. stop_job - Stop a running job
    {
        "commandId": 130,
        "type": "stop_job",
        "forecastId": "uuid",
        "data": {
            "modelType": "anomaly" | "forecast"  // optional, defaults to both
        }
    }

    9. pause_job - Pause a running job
    {
        "commandId": 131,
        "type": "pause_job",
        "forecastId": "uuid",
        "data": {
            "modelType": "anomaly" | "forecast"
        }
    }

    10. unpause_job - Resume a paused job
    {
        "commandId": 132,
        "type": "unpause_job",
        "forecastId": "uuid",
        "data": {
            "modelType": "anomaly" | "forecast"
        }
    }

    11. ping - Health check
    {
        "commandId": 133,
        "type": "ping"
    }
    """
    await websocket.accept()

    # Track subscriptions for this connection
    prediction_subscriptions: Dict[str, Set[str]] = {}  # {forecastId: {modelTypes}}
    log_subscriptions: Set[str] = set()  # {forecastIds}
    log_callbacks: Dict[str, Callable] = {}  # {model_id: callback_function}
    job_status_callbacks: Dict[str, Callable] = {}  # {model_id: callback_function}
    last_iterations: Dict[str, int] = {}  # {model_id: last_iteration}

    try:
        # Send connection confirmation
        await websocket.send_json(
            {
                "type": "connection",
                "message": "Connected to unified model service",
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )

        # Create task for subscription updates
        async def subscription_updater():
            """Background task to send prediction subscription updates (logs are now real-time)"""
            print(f"[SUBSCRIPTION UPDATER] Background task started for prediction updates")
            while True:
                try:
                    # Send prediction updates
                    for forecast_id, model_types in prediction_subscriptions.items():
                        for model_type in model_types:
                            model_id = (
                                f"{forecast_id}/{model_type}_predictor"
                                if model_type == "anomaly"
                                else f"{forecast_id}/forecast_model"
                            )

                            # Check if job has new iterations
                            job_status = get_job_status(model_id)
                            if job_status and job_status.get("status") == "running":
                                current_iteration = job_status.get("iterations", 0)
                                last_iteration = last_iterations.get(model_id, 0)

                                if current_iteration > last_iteration:
                                    # Send prediction update (Java backend expects 'model' field)
                                    await websocket.send_json(
                                        {
                                            "type": "prediction",
                                            "forecastId": forecast_id,
                                            "model": model_type,  # Java backend uses 'model' not 'modelType'
                                            "data": {
                                                "iteration": current_iteration,
                                                "status": job_status.get("status"),
                                                "last_run": job_status.get("last_run"),
                                            },
                                            "timestamp": datetime.now().isoformat() + "Z",
                                        }
                                    )
                                    last_iterations[model_id] = current_iteration

                    # Wait before next check (logs are now sent in real-time via callbacks)
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Error in subscription updater: {str(e)}")
                    await asyncio.sleep(5)

        # Start subscription updater task
        # updater_task = asyncio.create_task(subscription_updater())

        # Main message handling loop
        while True:
            message = await websocket.receive_json()

            command_id = message.get("commandId")
            msg_type = message.get("type")
            forecast_id = message.get("forecastId")
            data = message.get("data", {})

            # Validate commandId (except for connection/ping messages from Java backend)
            if command_id is None and msg_type not in ["connection", "ping"]:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Missing required field: commandId",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            # Handle ping
            if msg_type == "ping":
                await websocket.send_json(
                    {
                        "commandId": command_id,
                        "type": "pong",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            # Validate forecastId for other types (except connection/ping)
            if not forecast_id and msg_type not in ["ping", "connection"]:
                await websocket.send_json(
                    {
                        "commandId": command_id,
                        "type": "error",
                        "message": "Missing required field: forecastId",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            # Handle activate command
            if msg_type == "activate":
                await handle_activate(websocket, command_id, forecast_id, data)
                continue

            # Handle job_status command
            if msg_type == "job_status":
                await handle_job_status(websocket, command_id, forecast_id)
                continue

            # Handle job_logs command
            if msg_type == "job_logs":
                await handle_job_logs(websocket, command_id, forecast_id, data)
                continue

            # Handle subscribe_predictions or job_listen command (both supported for compatibility)
            if msg_type == "subscribe_predictions" or msg_type == "job_listen":
                # For job_listen, modelType is at top level (ThingsBoard pattern)
                model_type = (
                    message.get("modelType")
                    if msg_type == "job_listen"
                    else data.get("modelType", "anomaly")
                )

                if forecast_id not in prediction_subscriptions:
                    prediction_subscriptions[forecast_id] = set()

                prediction_subscriptions[forecast_id].add(model_type)

                # Initialize last iteration tracker
                model_id = (
                    f"{forecast_id}/{model_type}_predictor"
                    if model_type == "anomaly"
                    else f"{forecast_id}/forecast_model"
                )
                job_status = get_job_status(model_id)
                if job_status:
                    last_iterations[model_id] = job_status.get("iterations", 0)

                await websocket.send_json(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "model": model_type,
                        "forecastId": forecast_id,
                        "data": {
                            "status": "listening",
                            "message": f"Now listening to {model_type} predictions for {forecast_id}",
                            "current_iteration": (
                                job_status.get("iterations", 0) if job_status else 0
                            ),
                        },
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            # Handle unsubscribe_predictions command
            if msg_type == "unsubscribe_predictions":
                model_type = data.get("modelType", "anomaly")

                if forecast_id in prediction_subscriptions:
                    prediction_subscriptions[forecast_id].discard(model_type)
                    if not prediction_subscriptions[forecast_id]:
                        del prediction_subscriptions[forecast_id]

                await websocket.send_json(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "message": f"Unsubscribed from {model_type} predictions for {forecast_id}",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            # Handle subscribe_logs command
            if msg_type == "subscribe_logs":
                log_subscriptions.add(forecast_id)

                # send existing logs as initial batch for forecast model
                # await handle_job_logs(websocket, command_id, forecast_id, data, "forecast_model")
                # # send existing logs as initial batch for anomaly model
                # await handle_job_logs(websocket, command_id, forecast_id, data, "anomaly_predictor")

                # Create a real-time callback for this WebSocket connection
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

                # Subscribe to anomaly predictor
                anomaly_model_id = f"{forecast_id}/anomaly_predictor"
                # print(f"[SUBSCRIBE DEBUG] Creating callback for {anomaly_model_id}", flush=True)
                
                callback = create_log_callback(
                    websocket, forecast_id, command_id, asyncio.get_running_loop()
                )
                log_callbacks[anomaly_model_id] = callback
                # print(f"[SUBSCRIBE DEBUG] Calling subscribe_to_logs({anomaly_model_id}, {id(callback)})", flush=True)
                subscribe_to_logs(anomaly_model_id, callback)
                
                # Subscribe to forecast model
                forecast_model_id = f"{forecast_id}/forecast_model"
                # print(f"[SUBSCRIBE DEBUG] Creating callback for {forecast_model_id}", flush=True)
                
                callback = create_log_callback(
                    websocket, forecast_id, command_id, asyncio.get_running_loop()
                )
                log_callbacks[forecast_model_id] = callback
                # print(f"[SUBSCRIBE DEBUG] Calling subscribe_to_logs({forecast_model_id}, {id(callback)})", flush=True)
                subscribe_to_logs(forecast_model_id, callback)

                await websocket.send_json(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "message": f"Subscribed to real-time logs for {forecast_id}",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            # Handle unsubscribe_logs command
            if msg_type == "unsubscribe_logs":
                log_subscriptions.discard(forecast_id)
                model_id = f"{forecast_id}/anomaly_predictor"

                # Unsubscribe the callback if it exists
                if model_id in log_callbacks:
                    unsubscribe_from_logs(model_id, log_callbacks[model_id])
                    del log_callbacks[model_id]

                model_id = f"{forecast_id}/forecast_model"

                # Unsubscribe the callback if it exists
                if model_id in log_callbacks:
                    unsubscribe_from_logs(model_id, log_callbacks[model_id])
                    del log_callbacks[model_id]

                await websocket.send_json(
                    {
                        "commandId": command_id,
                        "type": "response",
                        "message": f"Unsubscribed from logs for {forecast_id}",
                        "timestamp": datetime.now().isoformat() + "Z",
                    }
                )
                continue

            # Handle stop_job command
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

                await websocket.send_json(
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

            # Handle pause_job command
            if msg_type == "pause_job":
                model_type = data.get("modelType", "forecast")

                if model_type == "anomaly":
                    model_id = f"{forecast_id}/anomaly_predictor"
                else:
                    model_id = f"{forecast_id}/forecast_model"

                success = pause_prediction_job(model_id)

                await websocket.send_json(
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

            # Handle unpause_job (resume) command
            if msg_type == "unpause_job":
                model_type = data.get("modelType", "forecast")

                if model_type == "anomaly":
                    model_id = f"{forecast_id}/anomaly_predictor"
                else:
                    model_id = f"{forecast_id}/forecast_model"

                success = unpause_prediction_job(model_id)

                await websocket.send_json(
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

            # Handle connection command (from Java backend)
            if msg_type == "connection":
                # Java backend sends connection confirmation, just acknowledge
                logger.info("Received connection message from Java backend")
                continue

            # Unknown command type
            await websocket.send_json(
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
        except:
            pass
    finally:
        # Cancel updater task
        if "updater_task" in locals():
            updater_task.cancel()

        # Clean up all log subscriptions for this connection
        for model_id, callback in log_callbacks.items():
            try:
                unsubscribe_from_logs(model_id, callback)
            except Exception as e:
                logger.error(f"Error unsubscribing from logs on cleanup: {str(e)}")
        
        # Clean up all job status subscriptions for this connection
        for model_id, callback in job_status_callbacks.items():
            try:
                unsubscribe_from_job_status(model_id, callback)
            except Exception as e:
                logger.error(f"Error unsubscribing from job status on cleanup: {str(e)}")

        logger.info("Unified WebSocket connection closed")


async def handle_activate(websocket: WebSocket, command_id: int, forecast_id: str, data: dict):
    """Handle model activation (training) command"""
    # model_id = f"{forecast_id}/forecast_model"
    # add_model_log(model_id, "info", f"calling train_and_save_model")
    # return

    try:
        # Send progress: initializing
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

        # Run synchronous data registry creation in thread pool to avoid blocking event loop

        data_registry = await asyncio.to_thread(get_data_registry)

        # Fetch device_id from configuration
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

        try:
            model_config = data_registry.fetch_predictive_model_config(forecast_id)
            device_id = model_config["device_id"]
        except Exception as e:
            traceback.print_exc()
            await websocket.send_json(
                {
                    "commandId": command_id,
                    "type": "error",
                    "message": f"Failed to fetch configuration: {str(e)}",
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )
            return

        # # Train AnomalyPredictor
        # await websocket.send_json(
        #     {
        #         "commandId": command_id,
        #         "type": "progress",
        #         "step": "training_anomaly",
        #         "message": "Training AnomalyPredictor...",
        #         "progress": 20,
        #         "timestamp": datetime.now().isoformat() + "Z",
        #     }
        # )
        
        # try:
        #     algorithm = model_config.get("anomaly_algorithm", None)
        #     print(f"[ACTIVATE] Starting anomaly predictor training...", flush=True)
        #     anomaly_result = await asyncio.to_thread(
        #         train_and_save_model,
        #         model_id=f"{forecast_id}/anomaly_predictor",
        #         model_type="AnomalyPredictor",
        #         device_id=device_id,
        #         data_registry=data_registry,
        #         algorithm=algorithm,
        #         days_back=90,
        #     )
        #     print(
        #         f"[ACTIVATE] Anomaly predictor training completed: {anomaly_result}",
        #         flush=True,
        #     )
        
        #     await websocket.send_json(
        #         {
        #             "commandId": command_id,
        #             "type": "progress",
        #             "step": "anomaly_complete",
        #             "message": "AnomalyPredictor trained successfully",
        #             "progress": 50,
        #             "metrics": anomaly_result.get("training_results", {}),
        #             "timestamp": datetime.now().isoformat() + "Z",
        #         }
        #     )
        # except Exception as e:
        #     error_trace = traceback.format_exc()
        #     print(f"[ACTIVATE ERROR] Training failed: {str(e)}", flush=True)
        #     print(f"[ACTIVATE ERROR] Traceback:\n{error_trace}", flush=True)
        #     await websocket.send_json(
        #         {
        #             "commandId": command_id,
        #             "type": "error",
        #             "step": "anomaly_failed",
        #             "message": f"AnomalyPredictor training failed: {str(e)}",
        #             "progress": 50,
        #             "timestamp": datetime.now().isoformat() + "Z",
        #         }
        #     )
        #     return  # Stop activation on training failure

        try:
            # Train ForecastModel
            # algorithm = model_config.get("forecast_algorithm", None)
            # algorithm = ""
            sensors = model_config.get("attributes", [])
            # map {'key': 'sensor'} to ['sensor']
            sensors = [sensor["key"] for sensor in sensors if "key" in sensor]

            # Extract aggregation functions per sensor
            aggregation_funcs = {
                sensor["key"]: sensor.get("aggregation", "average")
                for sensor in model_config.get("attributes", [])
                if "key" in sensor
            }

            # Extract per-sensor grouping intervals from attributes
            # Accept either the newer UI field `groupByMs` or legacy `grouping_interval_ms`.
            # Fallback to global forecast_grouping_ms if not set per-sensor.
            default_group_by_ms = model_config.get("forecast_grouping_ms", 5000)
            group_by_ms_per_sensor = {}
            for sensor in model_config.get("attributes", []):
                if "key" in sensor:
                    sensor_key = sensor["key"]
                    # Use per-sensor grouping interval if available, else try legacy key, else default
                    sensor_group_by_ms = (
                        sensor.get("groupByMs")
                        if sensor.get("groupByMs") is not None
                        else sensor.get("grouping_interval_ms", default_group_by_ms)
                    )
                    group_by_ms_per_sensor[sensor_key] = sensor_group_by_ms

            # For backward compatibility, keep group_by_ms as default
            group_by_ms = default_group_by_ms

            forecast_result = await asyncio.to_thread(
                train_and_save_model,
                model_id=f"{forecast_id}/forecast_model",
                model_type="ForecastModel",
                device_id=device_id,
                data_registry=data_registry,
                # algorithm=algorithm,
                # train_start_date=datetime(2014, 1, 1),
                # train_end_date=datetime(2016, 1, 1),
                sensors=sensors,
                lookback=20,
                group_by_ms=group_by_ms,
                group_by_ms_per_sensor=group_by_ms_per_sensor,
                aggregation_funcs=aggregation_funcs,
            )
            await websocket.send_json(
                {
                    "commandId": command_id,
                    "type": "progress",
                    "step": "forecast_complete",
                    "message": "ForecastModel trained successfully",
                    "progress": 90,
                    "metrics": forecast_result.get("training_results", {}),
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )
        except Exception as e:
            error_trace = traceback.format_exc()
            await websocket.send_json(
                {
                    "commandId": command_id,
                    "type": "error",
                    "step": "forecast_failed",
                    "message": f"ForecastModel training failed: {str(e)}",
                    "progress": 90,
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )
            return  # Stop activation on training failure

        # return
        # Start prediction job
        # print(f"[ACTIVATE] Starting prediction job...")
        # await asyncio.to_thread(
        #     start_prediction_job,
        #     f"{forecast_id}/anomaly_predictor",
        #     "AnomalyPredictor",
        #     device_id,
        # )
        # print(f"[ACTIVATE] Prediction job started")

        # forecast predictions
        # logger.info(f"[ACTIVATE] Starting ForecastModel prediction job for {forecast_id}")
        # job_started = await asyncio.to_thread(
        #     start_prediction_job,
        #     f"{forecast_id}/forecast_model",
        #     "ForecastModel",
        #     device_id,
        #     group_by_ms_per_sensor=group_by_ms_per_sensor,
        #     aggregation_funcs=aggregation_funcs,
        # )
        # logger.info(f"[ACTIVATE] ForecastModel prediction job start result: {job_started}")

        # Send completion
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
        await websocket.send_json(
            {
                "commandId": command_id,
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat() + "Z",
            }
        )


async def handle_job_status(websocket: WebSocket, command_id: int, forecast_id: str, job_status_callbacks: Dict[str, Callable] = None):
    """Handle job status request and subscribe to future updates"""
    try:
        # Helper function to create status update callback
        def create_status_callback(ws, fid, cmd_id, loop, model_type_str):
            logger.info(f"Creating job status callback for {fid} - {model_type_str}")
            def status_callback(status_data):
                """Callback to send status updates immediately when they change (thread-safe)"""
                try:
                    logger.info(f"Job status update for {fid} - {model_type_str}: {status_data}")
                    asyncio.run_coroutine_threadsafe(
                        ws.send_json(
                            {
                                "commandId": cmd_id,
                                "type": "response",
                                "model": "job",
                                "model_type": model_type_str,
                                "data": status_data,
                                "forecastId": fid,
                                "timestamp": datetime.now().isoformat() + "Z",
                            }
                        ),
                        loop,
                    )
                except Exception as e:
                    logger.error(f"Error sending real-time status update: {str(e)}")
            return status_callback
        
        # Handle anomaly predictor
        model_id = f"{forecast_id}/anomaly_predictor"
        job_status_anomaly = get_job_status(model_id)
        logger.info(f"Fetched job status for {model_id}: {job_status_anomaly}")

        if job_status_anomaly:
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
            
            # Subscribe to future status updates for anomaly predictor
            callback = create_status_callback(
                websocket, forecast_id, command_id, asyncio.get_running_loop(), "anomaly"
            )
            job_status_callbacks[model_id] = callback
            subscribe_to_job_status(model_id, callback)
        else:
            path = f"{forecast_id}/anomaly_predictor"
            await websocket.send_json(
                {
                    "commandId": command_id,
                    "type": "response",
                    "model": "job",
                    "forecastId": forecast_id,
                    "data": {
                        "status": "inactive",
                        # check if model files exist
                        "model_exists": (Path(settings.models_path) / path).exists(),
                    },
                    "timestamp": datetime.now().isoformat() + "Z",
                }
            )

        # Handle forecast model
        model_id = f"{forecast_id}/forecast_model"
        job_status_forecast = get_job_status(model_id)
        logger.info(f"Fetched job status for {model_id}: {job_status_forecast}")
        if job_status_forecast:
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
            
            callback = create_status_callback(
                websocket, forecast_id, command_id, asyncio.get_running_loop(), "forecast"
            )
            job_status_callbacks[model_id] = callback
            subscribe_to_job_status(model_id, callback)
        else:
            path = f"{forecast_id}/forecast_model"
            await websocket.send_json(
                {
                    "commandId": command_id,
                    "type": "response",
                    "model": "job",
                    "forecastId": forecast_id,
                    "data": {
                        "status": "inactive",
                        # check if model files exist
                        "model_exists": (Path(settings.models_path) / path).exists(),
                    },
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


async def handle_job_logs(
    websocket: WebSocket, command_id: int, forecast_id: str, data: dict, source: str
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
