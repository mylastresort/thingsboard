#!/bin/sh
set -e

# Start the real langfuse server in the background
dumb-init -- ./web/entrypoint.sh node ./web/server.js --keepAliveTimeout 110000 &
LANGFUSE_PID=$!

# Wait for langfuse to be ready
echo "[langfuse-entrypoint] waiting for langfuse..."
until wget -qO- http://127.0.0.1:3000/api/public/health >/dev/null 2>&1; do
  sleep 2
done
echo "[langfuse-entrypoint] langfuse is up"

# Register Ollama model definitions so Langfuse can infer costs
PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:-}"
SECRET_KEY="${LANGFUSE_SECRET_KEY:-}"

if [ -n "$PUBLIC_KEY" ] && [ -n "$SECRET_KEY" ]; then
  AUTH_HEADER="Authorization: Basic $(printf '%s:%s' "$PUBLIC_KEY" "$SECRET_KEY" | tr -d '\n' | base64 -w0)"

  for MODEL in \
    "glm-4.7-flash|(?i)^(ollama_chat/)?glm-4[._-]7[._-]flash" \
    "qwen3|(?i)^qwen3" \
  ; do
    NAME=$(echo "$MODEL" | cut -d'|' -f1)
    PATTERN=$(echo "$MODEL" | cut -d'|' -f2)
    echo "[langfuse-entrypoint] registering model: $NAME"
    wget -q -O /dev/null \
      --post-data="{\"modelName\":\"$NAME\",\"matchPattern\":\"$PATTERN\",\"unit\":\"TOKENS\",\"inputPrice\":0.00000006,\"outputPrice\":0.0000004}" \
      --header="Content-Type: application/json" \
      --header="$AUTH_HEADER" \
      "http://127.0.0.1:3000/api/public/models" 2>/dev/null || \
      echo "[langfuse-entrypoint] WARNING: failed to register $NAME"
  done
  echo "[langfuse-entrypoint] model registration complete"
else
  echo "[langfuse-entrypoint] no API keys — skipping model registration"
fi

# Keep langfuse in the foreground
wait $LANGFUSE_PID
