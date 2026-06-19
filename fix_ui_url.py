import re

with open("ui-ngx/src/app/core/http/forecast.service.ts", "r") as f:
    text = f.read()

text = text.replace(
    "private baseUrlModels = '/api/models';",
    "private baseUrlModels = '/api/v1/models';"
)

with open("ui-ngx/src/app/core/http/forecast.service.ts", "w") as f:
    f.write(text)
