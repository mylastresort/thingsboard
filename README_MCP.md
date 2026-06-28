# ThingsBoard MCP Server

Connects Claude Desktop to your local ThingsBoard instance via the [Model Context Protocol](https://modelcontextprotocol.io/), exposing 124 tools for devices, assets, telemetry, alarms, relations, and more.

## Architecture

```
Claude Desktop (Windows)
    └── cmd.exe → npx mcp-remote (Windows)
                      └── SSE → localhost:8201
                                    └── thingsboard-mcp (Docker / WSL2)
                                              └── REST → thingsboard:8080 (Docker)
```

The `thingsboard-mcp` container runs inside the Docker Compose stack on WSL2 and exposes port `8201` on the host. `mcp-remote` on Windows bridges Claude Desktop's STDIO transport to the container's SSE endpoint.

## Prerequisites

- Docker Compose stack running (`make up`)
- Node.js installed on Windows (for `npx`)
- Claude Desktop

## Docker Compose

`docker-compose/docker-compose.mcp.yml`:

```yaml
services:
  thingsboard-mcp:
    image: thingsboard/mcp
    restart: unless-stopped
    environment:
      THINGSBOARD_URL: "http://thingsboard:8080"
      THINGSBOARD_API_KEY: "${TB_MCP_API_KEY:-}"
      THINGSBOARD_USERNAME: "${TB_MCP_USERNAME:-tenant@thingsboard.org}"
      THINGSBOARD_PASSWORD: "${TB_MCP_PASSWORD:-tenant}"
      SPRING_AI_MCP_SERVER_STDIO: "false"
      SPRING_WEB_APPLICATION_TYPE: servlet
      HTTP_BIND_ADDRESS: "0.0.0.0"
      HTTP_BIND_PORT: "8000"
    ports:
      - "${MCP_PORT:-8201}:8000"
    depends_on:
      - thingsboard
```

The container listens on port `8000` internally, mapped to `8201` on the host. Override via `.env`:

```sh
TB_MCP_USERNAME=tenant@thingsboard.org
TB_MCP_PASSWORD=tenant
TB_MCP_API_KEY=          # preferred for TB 4.3+, leave blank to use username/password
MCP_PORT=8201
```

## Claude Desktop Config

`%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "thingsboard": {
      "command": "C:\\Windows\\System32\\cmd.exe",
      "args": [
        "/C",
        "C:\\Program Files\\nodejs\\npx.cmd",
        "mcp-remote",
        "http://localhost:8201/sse",
        "--transport",
        "sse"
      ]
    }
  }
}
```

> **`--transport sse` is required.** Without it, `mcp-remote` tries Streamable HTTP first,
> gets a 404, and the tool calls time out before the SSE fallback completes.

## Make Targets

```sh
make logs-mcp       # tail container logs
make restart-mcp    # restart the container
make shell-mcp      # sh into the container
make recreate-mcp   # force-recreate (pick up env/port changes)
```

## Troubleshooting

| Symptom                       | Cause                              | Fix                                                                         |
| ----------------------------- | ---------------------------------- | --------------------------------------------------------------------------- |
| `spawn npx ENOENT`            | Node not in Claude Desktop's PATH  | Use full path to `npx.cmd` in config                                        |
| `URL must start with 'https'` | Settings UI rejects `http://`      | Use `claude_desktop_config.json` instead                                    |
| Tool calls time out           | `mcp-remote` using wrong transport | Add `--transport sse` to args                                               |
| `Connected` but tools fail    | Wrong TB credentials               | Set `TB_MCP_USERNAME`/`TB_MCP_PASSWORD` in `.env`, then `make recreate-mcp` |
| Still `8000->8000` after edit | Container not recreated            | `make recreate-mcp` (restart alone doesn't apply port changes)              |
