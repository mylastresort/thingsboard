from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool
from .subagents import build_model, build_subagents
from shared.settings import load_settings, Settings

ROOT_INSTRUCTION = (
    "You are the ThingsBoard operations assistant. You have no ThingsBoard "
    "tools of your own — each of these tools is a specialist you call and "
    "whose answer you relay to the user: devices_agent, assets_agent, "
    "customers_users_agent, alarms_agent, telemetry_agent, "
    "relations_query_agent, ota_agent. Call whichever ones the request needs "
    "(more than one if it spans domains), then answer the user yourself from "
    "what they return."
)


def build_root_agent(settings: Settings) -> LlmAgent:
    return LlmAgent(
        name="thingsboard_ops_agent",
        model=build_model(settings),
        instruction=ROOT_INSTRUCTION,
        tools=[AgentTool(agent=a) for a in build_subagents(settings)],
    )


settings = load_settings()

root_agent = build_root_agent(settings)
