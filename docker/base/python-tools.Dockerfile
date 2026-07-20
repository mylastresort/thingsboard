# Shared Python base image for services that need mosquitto-clients, JDK, Node.js.
# Used by: predictive-maintenance workers, pdm-model-store, ws-events
#
# Build:  docker build -f docker/base/python-tools.Dockerfile -t tb-python-tools docker/base/
FROM python:3.12-slim

LABEL org.opencontainers.image.title="tb-python-tools" \
      org.opencontainers.image.description="Shared Python base with mosquitto-clients, JDK, Node.js, curl" \
      org.opencontainers.image.source="https://github.com/mylastresort/thingsboard"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       mosquitto-clients \
       default-jdk-headless \
       nodejs npm \
       curl \
    && rm -rf /var/lib/apt/lists/*
