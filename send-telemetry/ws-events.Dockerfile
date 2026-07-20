# syntax=docker/dockerfile:1.7

FROM tb-python-tools:latest

WORKDIR /app/send-telemetry

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

CMD [ "tail", "-f"]
