import re

with open("predictive-maintenance/src/forecast/forecast.py", "r") as f:
    text = f.read()

target = """@router.post("", summary="Create a forecast config", status_code=201)
async def create_forecast(body: ForecastCreate):
    import time as _time
    now = int(_time.time() * 1000)
    import uuid
    new_id = str(uuid.uuid4())
    tenant_id = body.tenantId.get("id") if body.tenantId else None
    device_id = body.deviceId.get("id") if body.deviceId else None
    
    with get_db_connection() as conn:
        if not tenant_id:
            # Fallback to get the first available tenant from the DB
            from sqlalchemy import text
            fallback_tenant = conn.execute(text("SELECT id FROM tenant LIMIT 1")).scalar()
            if fallback_tenant:
                tenant_id = str(fallback_tenant)
            else:
                # Use a dummy UUID if DB is absolutely empty (rare)
                tenant_id = "13814000-1dd2-11b2-8080-808080808080\""""

text = re.sub(
    r'@router\.post\("", summary="Create a forecast config", status_code=201\)\nasync def create_forecast\(body: ForecastCreate\):\n    import time as _time\n    now = int\(_time\.time\(\) \* 1000\)\n    import uuid\n    new_id = str\(uuid\.uuid4\(\)\)\n    tenant_id = body\.tenantId\.get\("id"\) if body\.tenantId else None\n    device_id = body\.deviceId\.get\("id"\) if body\.deviceId else None\n    with get_db_connection\(\) as conn:',
    target + "\n        row = conn.execute(",
    text
)

with open("predictive-maintenance/src/forecast/forecast.py", "w") as f:
    f.write(text)
