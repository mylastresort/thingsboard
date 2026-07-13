# go-toolbox

Small Go toolbox units used by the local ThingsBoard development stack.

## Units

- `interpreter`: interactive `pmtool` dispatcher for toolbox commands.
- `dash`: simulate devices that publish telemetry over MQTT.
- `darktheme`: append dark-theme CSS blocks to `ui-ngx` SCSS files.
- `failuremode`: HTTP API for failure-mode history and record management, generated from `cmd/failuremode/openapi.yaml` and backed by GORM/Postgres.

## Failure Mode API

Run migrations:

```sh
make failuremode-migrate
```

Run the service through compose:

```sh
docker compose --project-directory . -f docker-compose/docker-compose.toolbox.yml up go-toolbox-failuremode
```
