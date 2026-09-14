#!/usr/bin/env bash
# up-services-sorted.sh — Start ThingsBoard core services sequentially in
# dependency order (least → most dependent), waiting for each to be healthy
# before starting the next.
#
# Ordering mirrors the depends_on graph in the core compose files:
#   Level 0 (no deps):      postgres, redis, kafka, minio, ollama, config-db
#   Level 1 (→L0):          schema-registry, kafka-init, langfuse-db-init, thingsboard
#   Level 2 (→L1):          tb-quarkus, tb-web-ui, config-api, thingsboard-mcp, langfuse, pdm-model-store
#   Level 3 (→L2):          proxy, pdm-forecast-worker ×N, pdm-anomaly-worker ×N, ai-agent-py
#
# Usage: ./scripts/up-services-sorted.sh
#
# Honors the same knobs as the Makefile: PROJECT, PDM_FORECAST_WORKERS,
# PDM_ANOMALY_WORKERS. Run from the repo root.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

PROJECT="${PROJECT:-thingsboard}"
FORECAST_WORKERS="${PDM_FORECAST_WORKERS:-5}"
ANOMALY_WORKERS="${PDM_ANOMALY_WORKERS:-5}"

# Core compose files (same set as CORE_FILES in the Makefile)
COMPOSE_FILES=(
  docker-compose/docker-compose.base.yml
  docker-compose/docker-compose.db.yml
  docker-compose/docker-compose.tb.yml
  docker-compose/docker-compose.gateway.yml
  docker-compose/docker-compose.web.yml
  docker-compose/docker-compose.model.yml
  docker-compose/docker-compose.config.yml
  docker-compose/docker-compose.mcp.yml
)

compose_args=()
for f in "${COMPOSE_FILES[@]}"; do
  compose_args+=( -f "$f" )
done

dc() {
  docker compose --project-directory "$REPO_DIR" "${compose_args[@]}" -p "$PROJECT" "$@"
}

# Start one service and block until it is ready. config-api is special-cased
# because its image lacks `curl`, so the compose healthcheck can never pass —
# we poll its /health endpoint from the host instead.
#
# One-shot init services (kafka-init, langfuse-db-init) are special-cased too:
# `compose up --wait` returns a non-zero exit when they complete, which would
# trip `set -e`. We poll for their `Exited (0)` state instead.
start() {
  local svc="$1"
  local scale="${2:-}"
  echo "=== [$(date +%H:%M:%S)] ${svc} ==="
  case "$svc" in
    kafka-init|langfuse-db-init)
      dc up -d --no-deps "$svc"
      local cid="" tries=0
      until [[ -n "$cid" && "$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null)" == "exited" ]]; do
        cid="$(dc ps -q "$svc")"
        tries=$((tries + 1))
        if [[ $tries -ge 60 ]]; then
          echo "ERROR: ${svc} did not finish within 120s"
          dc logs --tail 30 "$svc"
          exit 1
        fi
        sleep 2
      done
      local code
      code="$(docker inspect -f '{{.State.ExitCode}}' "$cid")"
      if [[ "$code" != "0" ]]; then
        echo "ERROR: ${svc} exited with code ${code}"
        dc logs --tail 30 "$svc"
        exit 1
      fi
      echo "  ${svc} completed successfully"
      ;;
    config-api)
      dc up -d --no-deps "$svc"
      local tries=0
      until curl -fsS -m 2 http://localhost:9000/health >/dev/null 2>&1; do
        tries=$((tries + 1))
        if [[ $tries -ge 60 ]]; then
          echo "ERROR: ${svc} did not respond on :9000/health within 120s"
          dc logs --tail 30 "$svc"
          exit 1
        fi
        sleep 2
      done
      echo "  ${svc} is up (health 200)"
      ;;
    *)
      if [[ -n "$scale" ]]; then
        dc up -d --no-deps --wait --scale "$scale" "$svc"
      else
        dc up -d --no-deps --wait "$svc"
      fi
      echo "  ${svc} is up"
      ;;
  esac
}

echo "Starting core services sequentially by dependency order (project=${PROJECT})"
echo "Worker scales: forecast=${FORECAST_WORKERS}, anomaly=${ANOMALY_WORKERS}"
echo ""

# Level 0 — no dependencies
for svc in postgres redis kafka minio ollama config-db; do
  start "$svc"
done

# Level 1 — depend on Level 0
for svc in schema-registry kafka-init langfuse-db-init thingsboard; do
  start "$svc"
done

# Level 2 — depend on Level 1
for svc in tb-quarkus tb-web-ui config-api thingsboard-mcp langfuse pdm-model-store; do
  start "$svc"
done

# Level 3 — most dependent
start proxy
start pdm-forecast-worker "pdm-forecast-worker=${FORECAST_WORKERS}"
start pdm-anomaly-worker "pdm-anomaly-worker=${ANOMALY_WORKERS}"
start ai-agent-py

echo ""
echo "=== All core services started ==="
dc ps --format "table {{.Name}}\t{{.Service}}\t{{.Status}}"