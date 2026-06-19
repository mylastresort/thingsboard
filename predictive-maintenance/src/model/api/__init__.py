"""
REST API __init__ - Combines all REST endpoints
"""

from fastapi import APIRouter
from src.model.shared import MODEL_TYPE_MAP
import json
from src.db_connector import get_db_connection
from sqlalchemy import text

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
            "INSERT INTO predictive_model_load_model_config (name, config) "
            "VALUES (:name, :config) "
        ),
        {"name": name, "config": json.dumps(config)},
    )
    # commit the transaction
    db_connection.commit()
    db_connection.close()

    print("Load model configuration saved:", load_model_config)
    
    return {"status": "Load model configuration saved successfully"}

@router.get("/loadModelConfig", summary="Get predictive maintenance load model configurations", response_model=dict)
async def get_load_model_configs():
    """
    Retrieves the predictive maintenance load model configurations.
    """

    db_connection = get_db_connection()
    result = db_connection.execute(text("SELECT name, config FROM predictive_model_load_model_config"))
    records = result.fetchall()
    db_connection.close()

    print("Load model configuration retrieved:", records)

    records = {record[0]: record[1] for record in records}
    
    return records
@router.get("/anomaly-history-predictions/{model_id}/{prediction_type}", summary="Fetch anomaly history predictions", response_model=dict)
async def get_anomaly_history_predictions(
    model_id: str, 
    prediction_type: str, 
    startTs: int = None, 
    endTs: int = None, 
    limit: int = 100
):
    try:
        query = "SELECT id, model_id, created_time, created_at, prediction_time, prediction_type, prediction_value FROM predictions WHERE model_id = :model_id"
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
            import json
            try:
                pred_value = json.loads(record[6]) if record[6] else {}
            except Exception:
                pred_value = record[6]
            
            predictions.append({
                "id": str(record[0]),
                "modelId": str(record[1]),
                "createdTime": record[2],
                "createdAt": record[3],
                "predictionTime": record[4].isoformat() if hasattr(record[4], "isoformat") else record[4],
                "predictionType": record[5],
                "predictionValue": pred_value
            })
            
        return {
            "predictions": predictions,
            "totalCount": len(predictions),
            "limit": limit
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"predictions": [], "totalCount": 0, "limit": limit}

@router.delete("/anomaly-history-predictions/{model_id}", summary="Delete anomaly history predictions", response_model=dict)
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
        
        return {"deletedCount": deleted_count, "message": f"Successfully deleted {deleted_count} predictions"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"deletedCount": 0, "message": "Failed to delete predictions"}
