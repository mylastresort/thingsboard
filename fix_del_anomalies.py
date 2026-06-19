import re

with open("predictive-maintenance/src/model/api/__init__.py", "r") as f:
    text = f.read()

target = """@router.delete("/anomaly-history-predictions/{model_id}", summary="Delete anomaly history predictions", response_model=dict)
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
"""

if "@router.delete(" not in text:
    text += "\n" + target

with open("predictive-maintenance/src/model/api/__init__.py", "w") as f:
    f.write(text)
