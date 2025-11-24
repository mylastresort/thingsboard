FROM python:3.12

RUN apt update

RUN apt install -y mosquitto-clients less

WORKDIR /app

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

WORKDIR /app/send-telemetry/

CMD ["bash", "-c", "./docker-entry-point-dashboard.sh"]
# CMD [ "tail", "-f"]
