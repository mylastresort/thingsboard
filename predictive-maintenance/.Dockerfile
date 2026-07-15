FROM python:3.12

RUN apt update

RUN apt install -y mosquitto-clients less

# JDK for generating Python API client from OpenAPI spec at container start
RUN apt install -y default-jdk-headless || true

WORKDIR /app/predictive-maintenance

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# COPY . /app/

EXPOSE 8000

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Use entrypoint script to conditionally enable file watching
ENTRYPOINT ["/docker-entrypoint.sh"]