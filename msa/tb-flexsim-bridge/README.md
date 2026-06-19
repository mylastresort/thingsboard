# TB-FlexSim Bridge

Node.js microservice that connects ThingsBoard and FlexSim in both directions.

## What it does

- Receives telemetry/events from ThingsBoard via HTTP webhook and forwards them to FlexSim.
- Receives telemetry from FlexSim via HTTP and publishes it to ThingsBoard over MQTT.
- Supports per-device ThingsBoard tokens via request body or static map.

## Endpoints

- `GET /health`
- `POST /api/v1/thingsboard/telemetry`
- `POST /api/v1/flexsim/telemetry`

## Quick start

1. Copy env file and adjust values.

```bash
cp .env.example .env
```

2. Install dependencies and run.

```bash
npm install
npm run start
```

3. Health check.

```bash
curl http://localhost:8095/health
```

## Request examples

FlexSim to ThingsBoard:

```bash
curl -X POST http://localhost:8095/api/v1/flexsim/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "deviceName": "pump_1",
    "telemetry": {
      "temperature": 72.4,
      "pressure": 1.8
    }
  }'
```

ThingsBoard to FlexSim (webhook body from Rule Engine):

```bash
curl -X POST http://localhost:8095/api/v1/thingsboard/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "msg": {"temperature": 70.2},
    "metadata": {"deviceName": "pump_1"},
    "msgType": "POST_TELEMETRY_REQUEST"
  }'
```

## Docker

```bash
docker build -t tb-flexsim-bridge .
docker run --rm -p 8095:8095 --env-file .env tb-flexsim-bridge
```

## ThingsBoard configuration

Use a Rule Chain node of type REST API Call or external webhook to POST to:

`http://<bridge-host>:8095/api/v1/thingsboard/telemetry`

## FlexSim configuration

Configure FlexSim logic to POST telemetry to:

`http://<bridge-host>:8095/api/v1/flexsim/telemetry`

with body:

```json
{
  "deviceName": "pump_1",
  "telemetry": {
    "key": 123
  }
}
```

You can also include `deviceToken` directly per request if needed.
