import re

with open("predictive-maintenance/src/model/api/__init__.py", "r") as f:
    text = f.read()

target = """@router.get("/anomaly-history-predictions/{model_id}/{prediction_type}", summary="Fetch anomaly history predictions", response_model=dict)
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
"""

if "anomaly-history-predictions" not in text:
    text += "\n" + target

with open("predictive-maintenance/src/model/api/__init__.py", "w") as f:
    f.write(text)
