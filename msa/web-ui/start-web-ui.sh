#!/bin/bash
echo "Starting ThingsBoard Web UI..."

export NODE_CONFIG_DIR="/usr/share/tb-web-ui/config"   # ← matches COPY above
export LOG_FOLDER="/usr/share/tb-web-ui/logs"
export NODE_ENV=production
export WEB_FOLDER="/usr/share/tb-web-ui/web"

cd /usr/share/tb-web-ui
exec node server.js