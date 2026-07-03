"""
REST API __init__ - Combines all REST endpoints
"""

import json
import traceback
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, model_validator
from sqlalchemy import text

from src.db_connector import get_db_connection
from src.logger import logger  # Global logger
from src.model.shared import MODEL_TYPE_MAP

# Create main REST API router
router = APIRouter(
    prefix="/models",
    tags=["models-rest"],
)


@router.get("/available", summary="Get available model types to train", response_model=dict)
async def get_available_models():
    """
    Returns available model types for training (e.g., AnomalyPredictor, ForecastModel).
    """
    models = {}
    for k, v in MODEL_TYPE_MAP.items():
        models[k] = [json.loads(json.dumps(item, default=str)) for item in v]

    return models


@router.post("/saveLoadConfig", summary="Save predictive maintenance load model configuration")
async def save_load_model_config(load_model_config: dict):
    """
    Saves the predictive maintenance load model configuration.
    """

    name = load_model_config.get("name")
    config = load_model_config.get("config")

    db_connection = get_db_connection()
    db_connection.execute(
        text(
            "INSERT INTO predictive_model_load_model_config (name, config) VALUES (:name, :config) "
        ),
        {"name": name, "config": json.dumps(config)},
    )
    # commit the transaction
    db_connection.commit()
    db_connection.close()

    print("Load model configuration saved:", load_model_config)

    return {"status": "Load model configuration saved successfully"}


@router.get(
    "/loadModelConfig",
    summary="Get predictive maintenance load model configurations",
    response_model=dict,
)
async def get_load_model_configs():
    """
    Retrieves the predictive maintenance load model configurations.
    """

    db_connection = get_db_connection()
    result = db_connection.execute(
        text("SELECT name, config FROM predictive_model_load_model_config")
    )
    records = result.fetchall()
    db_connection.close()

    print("Load model configuration retrieved:", records)

    records = {record[0]: record[1] for record in records}

    return records


@router.get(
    "/anomaly-history-predictions/{model_id}/{prediction_type}",
    summary="Fetch anomaly history predictions",
    response_model=dict,
)
async def get_anomaly_history_predictions(
    model_id: str, prediction_type: str, startTs: int = None, endTs: int = None, limit: int = 100
):
    try:
        query = (
            "SELECT id, model_id, created_time, created_at, prediction_time, "
            "prediction_type, prediction_value FROM predictions WHERE model_id = :model_id"
        )
        params = {"model_id": model_id}

        if startTs is not None:
            query += " AND created_time >= :startTs"
            params["startTs"] = startTs
        if endTs is not None:
            query += " AND created_time <= :endTs"
            params["endTs"] = endTs

        if prediction_type and prediction_type.strip() != "":
            query += " AND prediction_type = :prediction_type"
            params["prediction_type"] = prediction_type

        query += " ORDER BY created_time DESC LIMIT :limit"
        params["limit"] = limit

        db_connection = get_db_connection()
        result = db_connection.execute(text(query), params)
        records = result.fetchall()
        db_connection.close()

        predictions = []
        for record in records:
            try:
                pred_value = json.loads(record[6]) if record[6] else {}
            except Exception:
                pred_value = record[6]

            predictions.append(
                {
                    "id": str(record[0]),
                    "modelId": str(record[1]),
                    "createdTime": record[2],
                    "createdAt": record[3],
                    "predictionTime": record[4].isoformat()
                    if hasattr(record[4], "isoformat")
                    else record[4],
                    "predictionType": record[5],
                    "predictionValue": pred_value,
                }
            )

        return {"predictions": predictions, "totalCount": len(predictions), "limit": limit}
    except Exception as e:
        traceback.print_exc()
        return {"predictions": [], "totalCount": 0, "limit": limit}


@router.delete(
    "/anomaly-history-predictions/{model_id}",
    summary="Delete anomaly history predictions",
    response_model=dict,
)
async def delete_anomaly_history_predictions(model_id: str, predictionType: str = None):
    try:
        query = "DELETE FROM predictions WHERE model_id = :model_id"
        params = {"model_id": model_id}

        if predictionType and predictionType.strip() != "":
            query += " AND prediction_type = :predictionType"
            params["predictionType"] = predictionType

        db_connection = get_db_connection()
        result = db_connection.execute(text(query), params)
        db_connection.commit()
        deleted_count = result.rowcount
        db_connection.close()

        return {
            "deletedCount": deleted_count,
            "message": f"Successfully deleted {deleted_count} predictions",
        }
    except Exception as e:
        traceback.print_exc()
        return {"deletedCount": 0, "message": "Failed to delete predictions"}


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
