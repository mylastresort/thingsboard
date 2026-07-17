#!/usr/bin/env bash
set -euo pipefail

SESSION_URI_FLAG=""
if [ -n "${SESSION_DB_URL:-}" ]; then
  SESSION_URI_FLAG="--session_service_uri=${SESSION_DB_URL}"
fi

exec adk api_server \
  --with_ui \
  --host 0.0.0.0 \
  --port "${PORT:-8300}" \
  ${SESSION_URI_FLAG} \
  thingsboard_ops_agent
