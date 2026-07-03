import asyncio
import json
from datetime import datetime
from random import randint

from fastapi import WebSocket

from src.logger import logger
from src.model.job import get_job_status, subscribe_to_job_status


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
