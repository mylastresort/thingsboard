import re

with open("predictive-maintenance/src/forecast/forecast.py", "r") as f:
    text = f.read()

# Fix double row = conn.execute( and unclosed parenthesis in the fallback addition
text = text.replace(
    'row = conn.execute(\n        row = conn.execute(',
    'row = conn.execute('
)

with open("predictive-maintenance/src/forecast/forecast.py", "w") as f:
    f.write(text)
