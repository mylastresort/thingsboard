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


def _getenv_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_settings() -> Settings:
    return Settings(
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "ibm/granite3.3:8b-instruct-q8_0"),
        ollama_num_ctx=_getenv_int("OLLAMA_NUM_CTX", 1024),
        mcp_server_url=os.environ.get(
            "MCP_SERVER_URL",
            os.environ.get("MCP_SERVER_DEFAULT_URL", "http://thingsboard-mcp:8000/sse"),
        ),
        max_steps=_getenv_int("MAX_STEPS", 8),
        max_tools_per_query=_getenv_int("MAX_TOOLS_PER_QUERY", 40),
        max_alarm_pages=_getenv_int("MAX_ALARM_PAGES", 1),
        max_observation_chars=_getenv_int("MAX_OBSERVATION_CHARS", 4000),
        port=_getenv_int("PORT", 8300),
    )
