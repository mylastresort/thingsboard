#!/bin/bash
set -e

cat <<'EOF'
============================================================
    PREDICTIVE MAINTENANCE MODEL SERVICE
============================================================

EOF

if [ "${PDM_PROCESS_ROLE,,}" = "worker" ]; then
  cat <<'EOF'
  MODE: KAFKA WORKER
  INBOUND API: DISABLED

============================================================

EOF
  exec python -m src.pdm_worker
fi

# Check if ENABLE_FILE_WATCH is set to true (case-insensitive)
if [ "${ENABLE_FILE_WATCH,,}" = "true" ]; then
  cat <<'EOF'
  MODE: DEVELOPMENT
  FILE WATCHING: ENABLED
  Auto-reload on code changes: YES

  Note: File watching adds overhead. Disable for production
        by setting ENABLE_FILE_WATCH=false

============================================================

EOF
  exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level warning --no-access-log
else
  cat <<'EOF'
  MODE: PRODUCTION
  FILE WATCHING: DISABLED
  Auto-reload on code changes: NO

  Note: For development with hot-reload, set
        ENABLE_FILE_WATCH=true

============================================================

EOF
  exec uvicorn main:app --host 0.0.0.0 --port 8000 --log-level warning --no-access-log
fi
