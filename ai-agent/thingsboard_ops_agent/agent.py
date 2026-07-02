from google.adk.agents import LlmAgent
from .instructions import INSTRUCTION
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from shared.settings import load_settings, Settings


def build_root_agent(settings: Settings) -> LlmAgent:
    return LlmAgent(
        name="thingsboard_ops_agent",
        model=LiteLlm(
            model=f"ollama_chat/{settings.ollama_model}",
            api_base=settings.ollama_base_url,
        ),
        instruction=INSTRUCTION,
        tools=[
            MCPToolset(
                connection_params=SseConnectionParams(url=settings.mcp_server_url)
            )
        ],
    )


settings = load_settings()

root_agent = build_root_agent(settings)
