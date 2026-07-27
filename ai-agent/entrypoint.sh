#!/usr/bin/env bash
set -euo pipefail

exec python3 /app/run_server.py "${PORT:-8300}" "${SESSION_SERVICE_URI:-}"
