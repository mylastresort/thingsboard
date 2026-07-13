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
exec python -m src.pdm_worker
