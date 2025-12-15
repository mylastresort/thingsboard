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