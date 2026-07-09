import pathlib

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset
from google.adk.tools.agent_tool import AgentTool

from .subagents import build_model, build_subagents
from .scope import build_scope_resolver, harvest_known_ids
from shared.settings import load_settings, Settings

SKILLS_DIR = pathlib.Path(__file__).parent / "skills"

find_site_asset_skill = load_skill_from_dir(SKILLS_DIR / "find-site-asset")
find_devices_in_site_skill = load_skill_from_dir(SKILLS_DIR / "find-devices-in-site")
get_timeseries_data_skill = load_skill_from_dir(SKILLS_DIR / "get-timeseries-data")
detect_machinery_anomalies_skill = load_skill_from_dir(
    SKILLS_DIR / "detect-machinery-anomalies"
)

ROOT_INSTRUCTION = (
    "You are the ThingsBoard operations assistant. You have no ThingsBoard "
    "tools of your own — each of these tools is a specialist you call and "
    "whose answer you relay to the user: devices_agent, assets_agent, "
    "customers_users_agent, alarms_agent, telemetry_agent, "
    "relations_query_agent, ota_agent. You also have four skills, "
    "find-site-asset, find-devices-in-site, get-timeseries-data, and "
    "detect-machinery-anomalies — check list_skills and load the relevant "
    "one whenever the request involves a building/site/facility name "
    "(find-site-asset / find-devices-in-site), asks for telemetry "
    "values/history/aggregates for one or more devices "
    "(get-timeseries-data), or asks to detect/flag/explain unusual "
    "vibration, temperature, pressure, or other telemetry changes "
    "(detect-machinery-anomalies — load this BEFORE calling any telemetry "
    "tool for that kind of request, since it requires asking the user which "
    "detection method they want before proceeding). Resolve device ids "
    "first (find-devices-in-site) before loading get-timeseries-data if the "
    "request only names a site. "
    "There is no dedicated device online/active/connectivity tool in the MCP "
    "server; when you need that kind of status, ask telemetry_agent for "
    "attributes such as active/inactivityAlarmTime or use "
    "relations_query_agent for EDQ/key-filter queries over those fields. "
    "Call whichever specialists the request needs (more than one if it spans "
    "domains), then answer the user yourself from what they return."
    "Never invent an id, count, or attribute value. If a tool errors or "
    "returns nothing, say so or call a lookup tool — do not retry with a "
    "different guessed value, and do not answer from what a similar entity "
    "'probably' has."
)


def build_root_agent(settings: Settings) -> LlmAgent:
    return LlmAgent(
        name="thingsboard_ops_agent",
        model=build_model(settings),
        instruction=ROOT_INSTRUCTION,
        before_agent_callback=build_scope_resolver(settings),
        after_tool_callback=harvest_known_ids,
        tools=[
            skill_toolset.SkillToolset(
                skills=[
                    find_site_asset_skill,
                    find_devices_in_site_skill,
                    get_timeseries_data_skill,
                    detect_machinery_anomalies_skill,
                ]
            ),
            *[AgentTool(agent=a) for a in build_subagents(settings)],
        ],
    )


settings = load_settings()
root_agent = build_root_agent(settings)
