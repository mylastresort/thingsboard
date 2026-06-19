import re

with open("predictive-maintenance/src/forecast/forecast.py", "r") as f:
    text = f.read()

# Add UUID import and handling
target = """@router.post("", summary="Create a forecast config", status_code=201)
async def create_forecast(body: ForecastCreate):
    import time as _time
    now = int(_time.time() * 1000)
    import uuid
    new_id = str(uuid.uuid4())"""

text = re.sub(
    r'@router\.post\("", summary="Create a forecast config", status_code=201\)\nasync def create_forecast\(body: ForecastCreate\):\n    import time as _time\n    now = int\(_time\.time\(\) \* 1000\)',
    target,
    text
)

# Update INSERT columns
text = text.replace(
    '"INSERT INTO predictive_maintenance_config "\n                "(name, created_time, tenant_id, device_id, attributes, "',
    '"INSERT INTO predictive_maintenance_config "\n                "(id, name, created_time, tenant_id, device_id, attributes, "'
)

# Update VALUES
text = text.replace(
    '"VALUES (:name, :created_time, :tenant_id, :device_id, CAST(:attributes AS jsonb), "',
    '"VALUES (CAST(:id AS uuid), :name, :created_time, :tenant_id, :device_id, CAST(:attributes AS jsonb), "'
)

# Update parameters
text = text.replace(
    '            {\n                "name": body.name,',
    '            {\n                "id": new_id,\n                "name": body.name,'
)

with open("predictive-maintenance/src/forecast/forecast.py", "w") as f:
    f.write(text)
