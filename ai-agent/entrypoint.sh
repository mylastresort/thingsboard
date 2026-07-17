#!/usr/bin/env bash
set -euo pipefail

SESSION_URI_FLAG=""
if [ -n "${SESSION_DB_URL:-}" ]; then
  SESSION_URI_FLAG="--session_service_uri=${SESSION_DB_URL}"

  # Ensure the ai_agent schema exists before ADK creates its tables.
  python3 -c "
import asyncio, asyncpg, os
async def _():
    url = os.environ['SESSION_DB_URL']
    # asyncpg needs postgresql:// not postgresql+asyncpg://
    url = url.replace('postgresql+asyncpg://', 'postgresql://')
    conn = await asyncpg.connect(url)
    await conn.execute('CREATE SCHEMA IF NOT EXISTS ai_agent')
    await conn.close()
asyncio.run(_())
" 2>/dev/null || echo "schema creation deferred (postgres not ready yet)"
fi

exec adk api_server \
  --with_ui \
  --host 0.0.0.0 \
  --port "${PORT:-8300}" \
  ${SESSION_URI_FLAG} \
  thingsboard_ops_agent
