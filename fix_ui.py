import re

with open("ui-ngx/src/app/core/http/forecast.service.ts", "r") as f:
    text = f.read()

# Replace baseUrl
text = text.replace(
    "private baseUrl = '/api/forecasts';",
    "private baseUrl = '/api/v1/forecast';"
)

with open("ui-ngx/src/app/core/http/forecast.service.ts", "w") as f:
    f.write(text)
