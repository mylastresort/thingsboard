# syntax=docker/dockerfile:1.7

FROM python:3.13-slim

LABEL org.opencontainers.image.title="ai-agent-py" \
      org.opencontainers.image.description="AI agent service with MCP integration"

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	UV_SYSTEM_PYTHON=1

WORKDIR /app

# Grab the uv binary directly (no pip bootstrap needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r /app/requirements.txt

COPY . /app
RUN uv pip install --system --no-cache .

COPY entrypoint.sh /app/entrypoint.sh
COPY run_server.py /app/run_server.py
RUN chmod +x /app/entrypoint.sh

EXPOSE 8300

ENTRYPOINT ["/app/entrypoint.sh"]
