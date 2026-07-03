import asyncio
from datetime import datetime
from random import randint
from typing import Callable, Dict

from fastapi import WebSocket

from src.logger import logger
from src.model.predictive_model import get_or_create_predictive_model, unsubscribe_from_model_status


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
