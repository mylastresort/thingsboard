import atexit
import pathlib

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset
from google.adk.tools.agent_tool import AgentTool

from .subagents import build_model, build_subagents, build_pandas_agent, build_pdm_agent
from .scope import build_scope_resolver, harvest_known_ids
from .settings import load_settings, Settings
from .datetime_tool import get_current_datetime
from .langfuse import after_model_callback as langfuse_after_model_callback, shutdown_langfuse
from .redis_session_service import register_redis_session_service

# Register the redis:// session service scheme so ADK's api_server picks it up
# when SESSION_SERVICE_URI=redis://... is provided.
register_redis_session_service()

SKILLS_DIR = pathlib.Path(__file__).parent / "skills"

find_site_asset_skill = load_skill_from_dir(SKILLS_DIR / "find-site-asset")
find_devices_in_site_skill = load_skill_from_dir(SKILLS_DIR / "find-devices-in-site")
get_timeseries_data_skill = load_skill_from_dir(SKILLS_DIR / "get-timeseries-data")
detect_machinery_anomalies_skill = load_skill_from_dir(
    SKILLS_DIR / "detect-machinery-anomalies"
)
seed_train_infer_pdm_skill = load_skill_from_dir(SKILLS_DIR / "seed-train-infer-pdm")
train_existing_device_pdm = load_skill_from_dir(SKILLS_DIR / "train-existing-device-pdm")

ROOT_INSTRUCTION = (
    # --- Identity & tool inventory -------------------------------------
    # Establishes that the root agent is purely an orchestrator: it holds
    # no ThingsBoard tools directly and must delegate everything to the
    # named specialist sub-agents, then relay their answers.
    "You are the ThingsBoard operations assistant. You have no ThingsBoard "
    "tools of your own — each of these tools is a specialist you call and "
    "whose answer you relay to the user: devices_agent, assets_agent, "
    "customers_users_agent, alarms_agent, telemetry_agent, "
    "relations_query_agent, ota_agent, pandas_agent, pdm_agent. "
    # --- pandas_agent delegation rule -----------------------------------
    # Fixes the observed failure mode where the root agent reasoned about
    # its own inability to run code ("I cannot run pandas in this
    # environment") instead of recognizing that limitation is precisely
    # why pandas_agent exists. States the rule twice — in plain terms and
    # again as a trigger-word list — since the model skipped this step
    # even though pandas_agent's existence was already documented.
    "You cannot execute Python, pandas, or any code yourself, and you must "
    "never state that you 'can't run pandas in this environment' or "
    "similar as a reason to skip, approximate, or reason through an "
    "analysis in your own head — that is exactly what pandas_agent is "
    "for. Any request containing words like mean, average, standard "
    "deviation, threshold, outlier, anomaly, trend, or correlation over "
    "telemetry or entity data is a pandas_agent call, not a reasoning "
    "task you attempt yourself. Fetch the raw data first, then hand it "
    "to pandas_agent inline via run_pandas_code_tool rather than "
    "expecting a file — never summarize statistics from raw numbers "
    "yourself. "
    # --- Skill routing ---------------------------------------------------
    # Maps request shapes to the four available skills. Each clause names
    # the trigger phrase pattern for one skill so the router doesn't have
    # to re-derive "which skill handles this" from first principles each
    # time. The detect-machinery-anomalies clause explicitly covers the
    # "already fully specified" case (Phase 0 of that skill), since a
    # fully-specified stats request was previously stalling instead of
    # triggering the skill at all.
    "You also have four skills, "
    "find-site-asset, find-devices-in-site, get-timeseries-data, and "
    "detect-machinery-anomalies — check list_skills and load the relevant "
    "one whenever the request involves a building/site/facility name "
    "(find-site-asset / find-devices-in-site), asks for telemetry "
    "values/history/aggregates for one or more devices "
    "(get-timeseries-data), or asks to detect/flag/explain unusual "
    "vibration, temperature, pressure, or other telemetry changes, "
    "including requests that already fully specify the statistical "
    "method (detect-machinery-anomalies — load this BEFORE calling any "
    "telemetry tool for that kind of request; if the request already "
    "answers all of the skill's elicitation questions, the skill closes "
    "its gate in the same turn with no questions asked), or asks to seed "
    "a PdM machine through the Quarkus MCP endpoint, create a predictive "
    "model, train it, or poll forecast/anomaly inference "
    "(seed-train-infer-pdm — load this BEFORE calling pdm_agent). "
    # --- Skill sequencing ------------------------------------------------
    # Prevents calling get-timeseries-data with an unresolved site/building
    # name instead of a concrete device id.
    "Resolve device ids first (find-devices-in-site) before loading "
    "get-timeseries-data if the request only names a site. "
    # --- Current-time grounding -------------------------------------------
    # Fixes the observed failure mode where the agent hallucinated "today's
    # date" from something the user said in prose (e.g. "the current time
    # is June 20, 2025") instead of checking the real clock, which then
    # corrupted every relative time-window calculation downstream.
    "You also have a get_current_datetime tool — call it any time a "
    "request involves a relative time window ('last 24 hours', 'this "
    "week', 'since yesterday', 'today') before computing timestamps. "
    "Never assume or infer the current date/time from conversation "
    "context or prior training data. "
    # --- Gap-filling guidance for device status ---------------------------
    # Documents a known MCP server gap (no dedicated connectivity/online
    # tool) and redirects to the correct workaround tools, so the agent
    # doesn't invent a nonexistent tool call or guess at device status.
    "There is no dedicated device online/active/connectivity tool in the "
    "MCP server; when you need that kind of status, ask telemetry_agent "
    "for attributes such as active/inactivityAlarmTime or use "
    "relations_query_agent for EDQ/key-filter queries over those fields. "
    # --- Multi-domain orchestration ----------------------------------------
    # Reminds the agent it's allowed (expected) to call more than one
    # specialist per request when the request spans domains, and that the
    # final answer is synthesized by the root agent, not just relayed
    # verbatim from a single sub-agent.
    "Call whichever specialists the request needs (more than one if it "
    "spans domains), then answer the user yourself from what they "
    "return."
    # --- Anti-hallucination guardrail ---------------------------------------
    # General-purpose backstop against invented data: covers ids, counts,
    # attribute values, and — critically — analogical guessing ("a similar
    # device probably has X"), which is a subtler hallucination pattern
    # than inventing a value outright.
    "Never invent an id, count, or attribute value. If a tool errors or "
    "returns nothing, say so or call a lookup tool — do not retry with a "
    "different guessed value, and do not answer from what a similar "
    "entity 'probably' has."
)


def build_root_agent(settings: Settings) -> LlmAgent:
    return LlmAgent(
        name="thingsboard_ops_agent",
        model=build_model(settings),
        instruction=ROOT_INSTRUCTION,
        before_agent_callback=build_scope_resolver(settings),
        after_model_callback=langfuse_after_model_callback,
        after_tool_callback=harvest_known_ids,
        tools=[
            skill_toolset.SkillToolset(
                skills=[
                    find_site_asset_skill,
                    find_devices_in_site_skill,
                    get_timeseries_data_skill,
                    detect_machinery_anomalies_skill,
                    # seed_train_infer_pdm_skill,
                    train_existing_device_pdm
                ]
            ),
            get_current_datetime,
            *[AgentTool(agent=a) for a in build_subagents(settings)],
            AgentTool(agent=build_pandas_agent(settings)),
            AgentTool(agent=build_pdm_agent(settings)),
        ],
    )


settings = load_settings()
root_agent = build_root_agent(settings)

atexit.register(shutdown_langfuse)
