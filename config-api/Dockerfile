# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

LABEL org.opencontainers.image.title="config-api" \
      org.opencontainers.image.description="Configuration API service"

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
