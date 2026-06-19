from fastapi import APIRouter, HTTPException
from pathlib import Path
import subprocess
from src.db_connector import SessionLocal, get_db_connection
from fastapi import Query, WebSocket, WebSocketDisconnect, Header
from fastapi.websockets import WebSocketState
from sqlalchemy import text
from src.db_connector import SessionLocal
import json
import websockets
import asyncio
import time
from src.forecast.predict import predict
from src.logger import logger  # Global logger
import requests
import sys
import os
from typing import Optional
from pydantic import BaseModel, model_validator

router = APIRouter(
    prefix="/forecast",
    tags=["forecast"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ForecastCreate(BaseModel):
    name: str
    tenantId: Optional[dict] = None  # {"entityType": "TENANT", "id": "..."}
    deviceId: Optional[dict] = None  # {"entityType": "DEVICE", "id": "..."}
    attributes: Optional[list] = []
    forecastAlgorithm: Optional[str] = "ARIMA"
    forecastStartDate: Optional[int] = 0
    forecastEndDate: Optional[int] = 0
    anomalyAlgorithm: Optional[str] = "THRESHOLD"
    anomalyStartDate: Optional[int] = 0
    anomalyEndDate: Optional[int] = 0
    viewPreferences: Optional[dict | str] = None
    additionalData: Optional[dict | str] = {}

    @model_validator(mode="before")
    @classmethod
    def parse_json_strings(cls, data: dict):
        if isinstance(data.get("viewPreferences"), str):
            try:
                data["viewPreferences"] = json.loads(data["viewPreferences"])
            except json.JSONDecodeError:
                pass
        if isinstance(data.get("additionalData"), str):
            try:
                data["additionalData"] = json.loads(data["additionalData"])
            except json.JSONDecodeError:
                pass
        return data


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


def _row_to_dict(row) -> dict:
    """Convert a DB row to a ThingsBoard-style PageData entity dict."""
    row_id = str(row[0])
    tenant_id = str(row[1]) if row[1] else None
    device_id = str(row[2]) if row[2] else None
    return {
        "id": {"entityType": "FORECAST", "id": row_id},
        "tenantId": {"entityType": "TENANT", "id": tenant_id},
        "deviceId": {"entityType": "DEVICE", "id": device_id},
        "createdTime": row[3],
        "name": row[4],
        "attributes": row[5] if row[5] is not None else [],
        "forecastAlgorithm": row[6],
        "forecastStartDate": row[7],
        "forecastEndDate": row[8],
        "anomalyAlgorithm": row[9],
        "anomalyStartDate": row[10],
        "anomalyEndDate": row[11],
        "viewPreferences": row[12],
        "additionalData": row[13] if row[13] is not None else {},
    }


@router.get("", summary="List forecast configs with pagination")
async def list_forecasts(
    pageSize: int = Query(10, ge=1, le=1000),
    page: int = Query(0, ge=0),
    sortProperty: Optional[str] = Query("createdTime"),
    sortOrder: Optional[str] = Query("DESC"),
    textSearch: Optional[str] = Query(None),
):
    allowed_sort = {"createdTime", "name", "deviceId"}
    sort_col = sortProperty if sortProperty in allowed_sort else "created_time"
    # map camelCase → snake_case column names
    col_map = {"createdTime": "created_time", "name": "name", "deviceId": "device_id"}
    sort_col = col_map.get(sortProperty, "created_time")
    order = "DESC" if (sortOrder or "DESC").upper() == "DESC" else "ASC"
    offset = page * pageSize

    with get_db_connection() as conn:
        # total count
        count_sql = "SELECT COUNT(*) FROM predictive_maintenance_config"
        params: dict = {}
        if textSearch:
            count_sql += " WHERE name ILIKE :search"
            params["search"] = f"%{textSearch}%"
        total = conn.execute(text(count_sql), params).scalar()

        # page query
        select_sql = (
            "SELECT id, tenant_id, device_id, created_time, name, attributes, "
            "forecast_algorithm, forecast_start_date, forecast_end_date, "
            "anomaly_algorithm, anomaly_start_date, anomaly_end_date, "
            "view_preferences, additional_data "
            "FROM predictive_maintenance_config"
        )
        if textSearch:
            select_sql += " WHERE name ILIKE :search"
        select_sql += f" ORDER BY {sort_col} {order} LIMIT :limit OFFSET :offset"
        params["limit"] = pageSize
        params["offset"] = offset
        rows = conn.execute(text(select_sql), params).fetchall()

    data = [_row_to_dict(r) for r in rows]
    return {
        "data": data,
        "totalPages": (total + pageSize - 1) // pageSize,
        "totalElements": total,
        "hasNext": (offset + pageSize) < total,
    }


@router.get("/{forecast_id}", summary="Get forecast config by id")
async def get_forecast(forecast_id: str):
    with get_db_connection() as conn:
        row = conn.execute(
            text(
                "SELECT id, tenant_id, device_id, created_time, name, attributes, "
                "forecast_algorithm, forecast_start_date, forecast_end_date, "
                "anomaly_algorithm, anomaly_start_date, anomaly_end_date, "
                "view_preferences, additional_data "
                "FROM predictive_maintenance_config WHERE id = :id"
            ),
            {"id": forecast_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Forecast not found")
    return _row_to_dict(row)


@router.post("", summary="Create a forecast config", status_code=201)
async def create_forecast(body: ForecastCreate, x_authorization: str = Header(None)):
    import time as _time
    import requests

    now = int(_time.time() * 1000)
    import uuid

    new_id = str(uuid.uuid4())
    tenant_id = body.tenantId.get("id") if body.tenantId else None
    device_id = body.deviceId.get("id") if body.deviceId else None

    if not tenant_id and x_authorization:
        try:
            # Fetch the actual tenant ID from the monolithic backend using the JWT token
            resp = requests.get(
                "http://thingsboard:8080/api/auth/user",
                headers={"X-Authorization": x_authorization},
                timeout=5,
            )
            if resp.status_code == 200:
                user_data = resp.json()
                fetched_tenant = user_data.get("tenantId", {}).get("id")
                if fetched_tenant:
                    tenant_id = fetched_tenant
        except Exception as e:
            logger.error(f"Failed to fetch user info from thingsboard backend: {e}")

    with get_db_connection() as conn:
        from sqlalchemy import text

        if not tenant_id:
            # Fallback to get the first available tenant from the DB
            fallback_tenant = conn.execute(text("SELECT id FROM tenant LIMIT 1")).scalar()
            if fallback_tenant:
                tenant_id = str(fallback_tenant)
            else:
                # Use a dummy UUID if DB is absolutely empty (rare)
                tenant_id = "13814000-1dd2-11b2-8080-808080808080"
        row = conn.execute(
            text(
                "INSERT INTO predictive_maintenance_config "
                "(id, name, created_time, tenant_id, device_id, attributes, "
                "forecast_algorithm, forecast_start_date, forecast_end_date, "
                "anomaly_algorithm, anomaly_start_date, anomaly_end_date, "
                "view_preferences, additional_data) "
                "VALUES (CAST(:id AS uuid), :name, :created_time, :tenant_id, :device_id, CAST(:attributes AS jsonb), "
                ":forecast_algorithm, :forecast_start_date, :forecast_end_date, "
                ":anomaly_algorithm, :anomaly_start_date, :anomaly_end_date, "
                "CAST(:view_preferences AS jsonb), CAST(:additional_data AS jsonb)) "
                "RETURNING id, tenant_id, device_id, created_time, name, attributes, "
                "forecast_algorithm, forecast_start_date, forecast_end_date, "
                "anomaly_algorithm, anomaly_start_date, anomaly_end_date, "
                "view_preferences, additional_data"
            ),
            {
                "id": new_id,
                "name": body.name,
                "created_time": now,
                "tenant_id": tenant_id,
                "device_id": device_id,
                "attributes": json.dumps(body.attributes),
                "forecast_algorithm": body.forecastAlgorithm or "ARIMA",
                "forecast_start_date": body.forecastStartDate or 0,
                "forecast_end_date": body.forecastEndDate or 0,
                "anomaly_algorithm": body.anomalyAlgorithm or "THRESHOLD",
                "anomaly_start_date": body.anomalyStartDate or 0,
                "anomaly_end_date": body.anomalyEndDate or 0,
                "view_preferences": json.dumps(
                    body.viewPreferences or {"selectedViews": ["forecast", "anomalies"]}
                ),
                "additional_data": json.dumps(body.additionalData or {}),
            },
        ).fetchone()
        conn.commit()
    return _row_to_dict(row)


@router.post("/{forecast_id}", summary="Update a forecast config")
async def update_forecast_config(forecast_id: str, body: ForecastCreate):
    device_id = body.deviceId.get("id") if body.deviceId else None
    with get_db_connection() as conn:
        row = conn.execute(
            text(
                "UPDATE predictive_maintenance_config SET "
                "name = :name, device_id = :device_id, attributes = CAST(:attributes AS jsonb), "
                "forecast_algorithm = :forecast_algorithm, forecast_start_date = :forecast_start_date, "
                "forecast_end_date = :forecast_end_date, anomaly_algorithm = :anomaly_algorithm, "
                "anomaly_start_date = :anomaly_start_date, anomaly_end_date = :anomaly_end_date, "
                "view_preferences = CAST(:view_preferences AS jsonb), additional_data = CAST(:additional_data AS jsonb) "
                "WHERE id = :id "
                "RETURNING id, tenant_id, device_id, created_time, name, attributes, "
                "forecast_algorithm, forecast_start_date, forecast_end_date, "
                "anomaly_algorithm, anomaly_start_date, anomaly_end_date, "
                "view_preferences, additional_data"
            ),
            {
                "id": forecast_id,
                "name": body.name,
                "device_id": device_id,
                "attributes": json.dumps(body.attributes),
                "forecast_algorithm": body.forecastAlgorithm or "ARIMA",
                "forecast_start_date": body.forecastStartDate or 0,
                "forecast_end_date": body.forecastEndDate or 0,
                "anomaly_algorithm": body.anomalyAlgorithm or "THRESHOLD",
                "anomaly_start_date": body.anomalyStartDate or 0,
                "anomaly_end_date": body.anomalyEndDate or 0,
                "view_preferences": json.dumps(body.viewPreferences or {}),
                "additional_data": json.dumps(body.additionalData or {}),
            },
        ).fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Forecast not found")
    return _row_to_dict(row)


@router.delete("/{forecast_id}", summary="Delete a forecast config")
async def delete_forecast(forecast_id: str):
    with get_db_connection() as conn:
        result = conn.execute(
            text("DELETE FROM predictive_maintenance_config WHERE id = :id"),
            {"id": forecast_id},
        )
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Forecast not found")
    return {"deleted": True, "id": forecast_id}


# ---------------------------------------------------------------------------

THINGSBOARD_WS_HOST_ADDR = "thingsboard"
THINGSBOARD_WS_PORT = 8080
THINGSBOARD_WS_URL = f"ws://{THINGSBOARD_WS_HOST_ADDR}:{THINGSBOARD_WS_PORT}/api/ws"
SCRIPTS_PATH = "/usr/share/thingsboard/data/predictive-maintenance/forecasts/"
TRAIN_SCRIPT = Path(SCRIPTS_PATH + "train.py")
DB_URL = SessionLocal.kw["bind"].url
FORECAST_WINDOW = 15
FORECAST_HISTORY_WINDOW = 10 * 24 * 60 * 60


@router.patch("/{forecast_id}/activate")
async def update_forecast(forecast_id: str):
    result = subprocess.run(
        [
            "python",
            str(TRAIN_SCRIPT),
            forecast_id,
            "--data-path",
            SCRIPTS_PATH,
            "--db-url",
            DB_URL,
        ],
        capture_output=True,
        text=True,
    )
    exitcode = result.returncode
    if exitcode != 0:
        ret = {"forecast_id": forecast_id, "status": "failed"}
        raise HTTPException(status_code=500, detail="Failed to update forecast")
    ret = {"forecast_id": forecast_id, "status": "active"}
    return ret


def to_timeseries_ws_cmd(
    device_id: str,
    attribute_keys: list,
    startTs: int,
    timeWindow: int,
    token: str,
):
    return {
        "authCmd": {
            "cmdId": 0,
            "token": token,
        },
        "cmds": [
            {
                "cmdId": 10,
                "entityType": "DEVICE",
                "entityId": device_id,
                "keys": ",".join(attribute_keys),
                "startTs": startTs,
                "timeWindow": timeWindow,
                "scope": "LATEST_TELEMETRY",
                "type": "TIMESERIES",
                # "limit": 20000,
            },
        ],
    }


def authenticate(username="tenant@thingsboard.org", password="tenant"):
    try:
        res = requests.post(
            f"http://{THINGSBOARD_WS_HOST_ADDR}:8080/api/auth/login",
            headers={"accept": "application/json", "Content-Type": "application/json"},
            data=json.dumps({"username": username, "password": password}),
        )
        body = res.json()
        return body["token"]
    except Exception as e:
        sys.exit(f"Fatal: login failed {e}")


@router.post("/{forecast_id}/routine/activate")
async def activate_forecast_routine(forecast_id: str, time_between_forecast: str):
    # logging.warning(f"time_between_forecasts {int(time_between_forecast)}")
    asyncio.create_task(
        forecast_routine(
            forecast_id=forecast_id,
            time_between_each_forecast=int(time_between_forecast),
            startTs=time.time(),
        )
    )
    return {"status": "success"}


async def forecast_routine(
    forecast_id: str,
    time_between_each_forecast: int,  # seconds
    startTs: float = Query(None),  # ms,
):
    token = authenticate()
    if startTs is None:
        startTs = int(time.time())
    startTs = int(startTs)
    session = SessionLocal()
    try:
        result = session.execute(
            text(
                f"SELECT device_id, attributes FROM forecast WHERE id = '{forecast_id}'",
            ),
        )
        result = result.fetchone()
        session.commit()
        device_id = str(result[0])
        attributes = result[1]
        attributes.append({"key": "datetime"})
        attribute_keys = [attr["key"] for attr in attributes]
        attribute_keys.append("datetime")
        result = session.execute(
            text(f"SELECT credentials_id FROM device_credentials where device_id = '{device_id}'"),
        )
        result = result.fetchone()
        session.commit()
        device_token = str(result[0])
        logger.warning(device_token)
        logger.warning("connected to websocket")
        # return
        while True:
            async with websockets.connect(THINGSBOARD_WS_URL) as ws:
                logger.warning("connected to thingsboard socket")
                try:
                    await ws.send(
                        json.dumps(
                            to_timeseries_ws_cmd(
                                device_id,
                                attribute_keys,
                                startTs,
                                int(time.time() * 1000),
                                token,
                            )
                        )
                    )
                    tm_data = {key: [] for key in attribute_keys}
                    while True:
                        try:
                            response = await asyncio.wait_for(ws.recv(), timeout=3)
                            response = json.loads(response)
                            if response["errorCode"] != 0:
                                raise Exception("Error in response")
                            response_data = response.get("data", None)
                            if not response_data or not response_data.get("pressure", None):
                                continue
                            for key in response_data.keys():
                                tm_data[key].extend(response_data[key])
                                tm_data[key] = tm_data[key][-25:]
                            if len(tm_data["pressure"]) >= 24 and len(tm_data["datetime"]) == len(
                                tm_data["pressure"]
                            ):
                                forecast_data = predict(tm_data, 1)
                                os.system(
                                    f"mosquitto_pub -d -q 1 -h thingsboard -p 1883 -t v1/devices/me/telemetry -u "
                                    + device_token
                                    + " -m "
                                    + "'{"
                                    + f"ts: {response_data['pressure'][-1][0] + time_between_each_forecast * 1000}, values:"
                                    + "{"
                                    + f"forecast:'{forecast_data['pressure'][0]}'"
                                    + "}}' >/dev/null"
                                )
                            else:
                                logger.warning(
                                    f"pressure: {len(tm_data['pressure'])}, datetime: {len(tm_data['datetime'])}"
                                )
                        except asyncio.exceptions.TimeoutError:
                            logger.warning("Timeout")
                            continue
                        except Exception as e:
                            logger.warning(f"Loop Exception: {e}")
                            return
                except WebSocketDisconnect as e:
                    logger.warning(f"WebSocketDisconnect: {e}")
    except asyncio.CancelledError as e:
        logger.warning(f"CancelledError: {e}")
    except Exception as e:
        logger.warning(f"Exception: {e}")


@router.websocket("/{forecast_id}/ws")
async def websocket_endpoint(
    client: WebSocket,
    forecast_id: str,
    x_authorization: str = Header(None),
    token: str = Query(None),
    startTs: int = Query(None),  # ms
    forecastWindow: int = Query(FORECAST_WINDOW),
):
    if not token and x_authorization is None:
        return await client.close()
    if not token:
        token = x_authorization.split(" ")[1]
    if startTs is None:
        startTs = int(time.time())
    startTs = int(startTs)
    session = SessionLocal()
    try:
        result = session.execute(
            text(
                f"SELECT device_id, attributes FROM forecast WHERE id = '{forecast_id}'",
            ),
        )
        result = result.fetchone()
        device_id = str(result[0])
        attributes = result[1]
        attributes.append({"key": "datetime"})
        attribute_keys = [attr["key"] for attr in attributes]
        attribute_keys.append("datetime")
        attribute_keys.append("forecast")
        await client.accept()
        await client.send_text(f"Connected to forecast {forecast_id}")
        logger.warning("connected to websocket")
        async with websockets.connect(THINGSBOARD_WS_URL) as ws:
            logger.warning("connected to thingsboard socket")
            try:
                await ws.send(
                    json.dumps(
                        to_timeseries_ws_cmd(
                            device_id,
                            attribute_keys,
                            startTs,
                            int(time.time() * 1000),
                            token,
                        )
                    )
                )
                tm_data = {key: [] for key in attribute_keys}
                forecast_data = {"pressure": [], "datetime": []}
                while True:
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=3)
                        response = json.loads(response)
                        # logging.warning(response)
                        if response["errorCode"] != 0:
                            raise Exception("Error in response")
                        response_data = response.get("data", None)
                        # logging.warning(f"keys: {response_data.keys()}")
                        if (
                            not response_data
                            or not response_data.get("pressure", None)
                            # or not response_data.get("forecast", None)
                        ):
                            continue
                        for key in response_data.keys():
                            tm_data[key].extend(response_data[key])
                            tm_data[key] = tm_data[key][-25:]
                        if len(tm_data["pressure"]) >= 24 and len(tm_data["pressure"]) == len(
                            tm_data["datetime"]
                        ):
                            forecast_data = predict(tm_data, forecastWindow)
                        await client.send_text(
                            json.dumps(
                                {
                                    "forecast": forecast_data,
                                    "lastestDataValue": response_data["pressure"][-1],
                                    # "data": response_data,
                                }
                            )
                        )
                    except asyncio.exceptions.TimeoutError:
                        logger.warning("Timeout")
                        if client.application_state == WebSocketState.CONNECTED:
                            await client.send_text("Keep Alive")
                        continue
                    except Exception as e:
                        logger.warning(f"Loop Exception: {e}")
                        break
            except WebSocketDisconnect as e:
                logger.warning(f"WebSocketDisconnect: {e}")
                # if ws.open:
                #     await ws.close()
    except asyncio.CancelledError as e:
        logger.warning(f"CancelledError: {e}")
        if client.application_state == WebSocketState.CONNECTED:
            await client.close()
    except Exception as e:
        logger.warning(f"Exception: {e}")
        await client.close()
