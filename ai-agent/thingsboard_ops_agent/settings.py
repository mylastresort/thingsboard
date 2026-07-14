import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    ollama_model: str
    ollama_num_ctx: int
    mcp_server_url: str
    max_steps: int
    max_tools_per_query: int
    max_alarm_pages: int
    max_observation_chars: int
    port: int
    tb_authority: str = "TENANT_ADMIN"
    tb_customer_id: str | None = None
    tb_tenant_id: str | None = None
    pandas_mcp_server_url: str = os.getenv("PANDAS_MCP_SERVER_URL", "http://pandas-mcp:8000/sse")
    pdm_mcp_server_url: str = os.getenv("PDM_MCP_SERVER_URL", "http://tb-quarkus:8081/mcp/sse")


def _getenv_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_settings() -> Settings:
    tb_authority = os.environ.get("TB_AUTHORITY", "TENANT_ADMIN").strip()
    if tb_authority not in {"SYS_ADMIN", "TENANT_ADMIN", "CUSTOMER_USER"}:
        raise ValueError(
            "TB_AUTHORITY must be one of SYS_ADMIN, TENANT_ADMIN, CUSTOMER_USER"
        )

    return Settings(
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "ibm/granite3.3:8b-instruct-q8_0"),
        ollama_num_ctx=_getenv_int("OLLAMA_NUM_CTX", 16000),
        mcp_server_url=os.environ.get(
            "MCP_SERVER_URL",
            os.environ.get("MCP_SERVER_DEFAULT_URL", "http://thingsboard-mcp:8000/sse"),
        ),
        max_steps=_getenv_int("MAX_STEPS", 8),
        max_tools_per_query=_getenv_int("MAX_TOOLS_PER_QUERY", 40),
        max_alarm_pages=_getenv_int("MAX_ALARM_PAGES", 1),
        max_observation_chars=_getenv_int("MAX_OBSERVATION_CHARS", 4000),
        port=_getenv_int("PORT", 8300),
        tb_authority=tb_authority,
        tb_customer_id=os.environ.get("TB_CUSTOMER_ID") or None,
        tb_tenant_id=os.environ.get("TB_TENANT_ID") or None,
    )
