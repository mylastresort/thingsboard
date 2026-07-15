#!/bin/bash
set -e

cat <<'EOF'
============================================================
    PREDICTIVE MAINTENANCE MODEL SERVICE
============================================================

EOF

cat <<'EOF'
  MODE: KAFKA WORKER
  INBOUND API: DISABLED

============================================================

EOF

# Generate Python API client from split OpenAPI spec (source is bind-mounted)
if [ ! -d /app/predictive-maintenance/quarkus_api_client ] && [ -d /app/tb-quarkus/gateway ]; then
    echo "Generating Python API client from OpenAPI spec..."
    cd /app/tb-quarkus/gateway && ./gradlew --no-daemon generatePythonApiClient 2>/dev/null || true
    cd /app/predictive-maintenance
fi

exec python -m src.pdm_worker
