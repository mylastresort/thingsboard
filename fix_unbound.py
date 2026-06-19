import re

with open("predictive-maintenance/src/forecast/forecast.py", "r") as f:
    text = f.read()

# Fix UnboundLocalError by moving `from sqlalchemy import text` to the top level or function level
text = text.replace(
    '        if not tenant_id:\n            # Fallback to get the first available tenant from the DB\n            from sqlalchemy import text',
    '        from sqlalchemy import text\n        if not tenant_id:\n            # Fallback to get the first available tenant from the DB'
)

with open("predictive-maintenance/src/forecast/forecast.py", "w") as f:
    f.write(text)
