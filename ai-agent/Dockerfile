FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	UV_SYSTEM_PYTHON=1

WORKDIR /app

# Grab the uv binary directly (no pip bootstrap needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY requirements.txt /app/requirements.txt
RUN uv pip install --system --no-cache -r /app/requirements.txt

COPY . /app

RUN pytest tests/ -v --tb=short

EXPOSE 8300

CMD ["adk", "api_server", "--with_ui", "--host", "0.0.0.0", "--port", "8300", "thingsboard_ops_agent"]