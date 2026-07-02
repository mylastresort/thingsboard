FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8300

# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8300"]

CMD ["adk", "api_server", "--with_ui", "--host", "0.0.0.0", "--port", "8300", "thingsboard_ops_agent"]
