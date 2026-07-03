from datetime import datetime

from fastapi import WebSocket

from src.model.job import get_model_logs


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
