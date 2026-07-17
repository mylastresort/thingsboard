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
RUN uv pip install --system --no-cache .

RUN pytest tests/ -v --tb=short

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8300

ENTRYPOINT ["/app/entrypoint.sh"]