import re

with open("predictive-maintenance/src/forecast/forecast.py", "r") as f:
    text = f.read()

target = """@router.post("", summary="Create a forecast config", status_code=201)
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
                timeout=5
            )
            if resp.status_code == 200:
                user_data = resp.json()
                fetched_tenant = user_data.get("tenantId", {}).get("id")
                if fetched_tenant:
                    tenant_id = fetched_tenant
        except Exception as e:
            logger.error(f"Failed to fetch user info from thingsboard backend: {e}")

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
    r'@router\.post\("", summary="Create a forecast config", status_code=201\)\nasync def create_forecast\(body: ForecastCreate\):\n    import time as _time\n    now = int\(_time\.time\(\) \* 1000\)\n    import uuid\n    new_id = str\(uuid\.uuid4\(\)\)\n    tenant_id = body\.tenantId\.get\("id"\) if body\.tenantId else None\n    device_id = body\.deviceId\.get\("id"\) if body\.deviceId else None\n    \n    with get_db_connection\(\) as conn:\n        if not tenant_id:\n            # Fallback to get the first available tenant from the DB\n            from sqlalchemy import text\n            fallback_tenant = conn\.execute\(text\("SELECT id FROM tenant LIMIT 1"\)\)\.scalar\(\)\n            if fallback_tenant:\n                tenant_id = str\(fallback_tenant\)\n            else:\n                # Use a dummy UUID if DB is absolutely empty \(rare\)\n                tenant_id = "13814000-1dd2-11b2-8080-808080808080"',
    target,
    text
)

with open("predictive-maintenance/src/forecast/forecast.py", "w") as f:
    f.write(text)
