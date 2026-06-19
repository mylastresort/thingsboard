import re

with open("predictive-maintenance/src/forecast/forecast.py", "r") as f:
    text = f.read()

# Fix the dummy UUID string ending with an unneeded quote
text = text.replace(
    'tenant_id = "13814000-1dd2-11b2-8080-808080808080\\\"',
    'tenant_id = "13814000-1dd2-11b2-8080-808080808080"'
)

# And fix any extra indentation misalignments if any
text = text.replace(
    'tenant_id = "13814000-1dd2-11b2-8080-808080808080"row = conn.execute(',
    'tenant_id = "13814000-1dd2-11b2-8080-808080808080"\n        row = conn.execute('
)

with open("predictive-maintenance/src/forecast/forecast.py", "w") as f:
    f.write(text)
