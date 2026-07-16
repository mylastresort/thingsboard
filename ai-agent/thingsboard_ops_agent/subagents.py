"""ThingsBoard domain sub-agents.

One LlmAgent per ThingsBoard domain, each wired to the *same* MCP server but
scoped down with MCPToolset's `tool_filter` so it only sees the tools for its
job. The root agent (see agent.py) does the routing via ADK's built-in
LLM-driven delegation (sub_agents=[...] -> transfer_to_agent), so no manual
dispatch logic is needed here.
"""

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from .settings import Settings
from .scope import (
    build_scoped_instruction,
    build_scoped_tool_filter,
    guard_scoped_tool_calls,
)

# name -> (description/instruction, tool_filter)
# Grouped from the ThingsBoard MCP server tools.
DOMAINS: dict[str, tuple[str, list[str]]] = {
    "devices_agent": (
        "Manages ThingsBoard devices: create/update, delete, look up, fetch "
        "credentials, and list devices by tenant, customer, user, ids, or "
        "entity group.",
        [
            "createOrUpsertDevice",
            "deleteDevice",
            "getCustomerDevices",
            "getDeviceById",
            "getDeviceCredentialsByDeviceId",
            "getDevicesByIds",
            "getDevicesByEntityGroupId",
            "getTenantDevice",
            "getTenantDevices",
            "getUserDevices",
            "saveDevice",
        ],
    ),
    "assets_agent": (
        "Manages ThingsBoard assets: create/update, delete, look up, and list "
        "assets by tenant, customer, user, or entity group.",
        [
            "deleteAsset",
            "getAssetById",
            "getAssetsByEntityGroupId",
            "getCustomerAssets",
            "getTenantAsset",
            "getTenantAssets",
            "getUserAssets",
            "saveAsset",
        ],
    ),
    "customers_users_agent": (
        "Manages ThingsBoard customers and users: create/update/delete and "
        "list them by tenant, customer, user, alarm assignment, or entity "
        "group.",
        [
            "deleteCustomer",
            "deleteUser",
            "getAllCustomerUsers",
            "getCustomerById",
            "getCustomerUsers",
            "getCustomers",
            "getCustomersByEntityGroupId",
            "getTenantAdmins",
            "getTenantCustomer",
            "getUserById",
            "getUserCustomers",
            "getUsers",
            "getUsersByEntityGroupId",
            "getUsersForAssign",
            "saveCustomer",
            "saveUser",
        ],
    ),
    "alarms_agent": (
        "Manages ThingsBoard alarms: acknowledge, clear, delete, create/update, "
        "and query alarms, their types, and severity.",
        [
            "ackAlarm",
            "clearAlarm",
            "deleteAlarm",
            "getAlarmInfoById",
            "getAlarmTypes",
            "getAlarms",
            "getAllAlarms",
            "getHighestAlarmSeverity",
            "saveAlarm",
        ],
    ),
    "telemetry_agent": (
        "Reads and writes ThingsBoard entity attributes and time-series "
        "telemetry; use this for device attributes like active/inactivityAlarmTime.",
        [
            "getAttributeKeys",
            "getAttributeKeysByScope",
            "getAttributes",
            "getAttributesByScope",
            "getLatestTimeseries",
            "getTimeseries",
            "getTimeseriesKeys",
            "saveDeviceAttributes",
            "saveEntityAttributesV2",
            "saveEntityTelemetry",
            "saveEntityTelemetryWithTTL",
        ],
    ),
    "relations_query_agent": (
        "Manages entity relations and entity groups, and provides the EDQ/query "
        "surface for entity data, counts, relations, and the EDQ/key-filter "
        "guides.",
        [
            "addEntitiesToEntityGroup",
            "countByApiUsageStateFilter",
            "countByAssetSearchQueryFilter",
            "countByAssetTypeFilter",
            "countByDeviceSearchQueryFilter",
            "countByDeviceTypeFilter",
            "countByEdgeQueryFilter",
            "countByEdgeTypeFilter",
            "countByEntitiesGroupNameFilter",
            "countByEntityGroupFilter",
            "countByEntityGroupListFilter",
            "countByEntityGroupNameFilter",
            "countByEntityListFilter",
            "countByEntityNameFilter",
            "countByEntityTypeFilter",
            "countByEntityViewSearchQueryFilter",
            "countByEntityViewTypeFilter",
            "countByRelationsQueryFilter",
            "countBySingleEntityFilter",
            "deleteEntityGroup",
            "deleteRelation",
            "deleteRelations",
            "findByFromWithRelationType",
            "findByToWithRelationType",
            "findEntityDataByApiUsageStateFilter",
            "findEntityDataByAssetSearchQueryFilter",
            "findEntityDataByAssetTypeFilter",
            "findEntityDataByDeviceSearchQueryFilter",
            "findEntityDataByDeviceTypeFilter",
            "findEntityDataByEdgeQueryFilter",
            "findEntityDataByEdgeTypeFilter",
            "findEntityDataByEntitiesGroupNameFilter",
            "findEntityDataByEntityGroupFilter",
            "findEntityDataByEntityGroupListFilter",
            "findEntityDataByEntityGroupNameFilter",
            "findEntityDataByEntityListFilter",
            "findEntityDataByEntityNameFilter",
            "findEntityDataByEntityTypeFilter",
            "findEntityDataByEntityViewSearchQueryFilter",
            "findEntityDataByEntityViewTypeFilter",
            "findEntityDataByRelationsQueryFilter",
            "findEntityDataBySingleEntityFilter",
            "findEntityDataByStateEntityOwnerFilter",
            "findInfoByFrom",
            "findInfoByTo",
            "getEdqCountGuide",
            "getEdqGuide",
            "getEntityGroupById",
            "getEntityGroupByOwnerAndNameAndType",
            "getEntityGroupsByIds",
            "getEntityGroupsByOwnerAndType",
            "getEntityGroupsByType",
            "getEntityGroupsForEntity",
            "getKeyFiltersGuide",
            "getRelation",
            "removeEntitiesFromEntityGroup",
            "saveEntityGroup",
            "saveRelation",
        ],
    ),
    "ota_agent": (
        "Manages ThingsBoard OTA firmware/software packages: create/update, "
        "delete, download, count device-profile coverage, and assign packages "
        "to devices or device profiles.",
        [
            "assignOtaPackageToDevice",
            "assignOtaPackageToDeviceProfile",
            "countByDeviceProfileAndEmptyOtaPackage",
            "deleteOtaPackage",
            "downloadOtaPackage",
            "getOtaPackageById",
            "getOtaPackageInfoById",
            "getOtaPackages",
            "getOtaPackagesByDeviceProfile",
            "saveOtaPackageData",
            "saveOtaPackageInfo",
        ],
    ),
}


def build_model(settings: Settings) -> LiteLlm:
    return LiteLlm(
        model=f"ollama_chat/{settings.ollama_model}",
        api_base=settings.ollama_base_url,
        num_ctx=settings.ollama_num_ctx,
    )


def build_subagents(settings: Settings) -> list[BaseAgent]:
    model = build_model(settings)
    agents: list[BaseAgent] = [
        LlmAgent(
            name=name,
            model=model,
            description=text,  # shown to the root as this tool's docstring
            instruction=build_scoped_instruction(name, text),
            tools=[
                MCPToolset(
                    connection_params=SseConnectionParams(url=settings.mcp_server_url),
                    tool_filter=build_scoped_tool_filter(name, tool_filter),
                )
            ],
            before_tool_callback=guard_scoped_tool_calls,
        )
        for name, (text, tool_filter) in DOMAINS.items()
    ]
    return agents


PANDAS_DOMAIN: tuple[str, tuple[str, list[str]]] = (
    "pandas_agent",
    (
        "Runs pandas-based statistical analysis and chart generation on "
        "tabular or timeseries data you pass in directly (e.g. telemetry "
        "pulled from ThingsBoard): read_metadata_tool, interpret_column_data, "
        "run_pandas_code_tool, generate_chartjs_tool. Use run_pandas_code_tool "
        "for stats/anomaly detection on data you already have in hand — you "
        "do not need a file on disk to use it.",
        [
            "read_metadata_tool",
            "interpret_column_data",
            "run_pandas_code_tool",
            "generate_chartjs_tool",
        ],
    ),
)


PDM_DOMAIN: tuple[str, tuple[str, list[str]]] = (
    "pdm_agent",
    (
        "Runs predictive-maintenance workflows through the Quarkus PdM MCP "
        "endpoint. Use it to create/update/delete model configs, manage load "
        "configs, train models, start inference, poll model/job status, fetch "
        "forecast or anomaly prediction history, manage failure mode records, "
        "and import failure mode CSVs. "
        "When creating a new model, you must first call getAvailableAlgorithmsMap "
        "to see the available algorithms for Forecast/AnomalyPredictor models, "
        "then pass the algorithm name and any parameters to the create tool.",
        [
            "getAvailableAlgorithmsMap",
            "getLoadModelConfigs",
            "getPredictiveModelsByPage",
            "getPredictiveModel",
            "getPredictiveModelStatus",
            "getPredictiveModelsByDeviceId",
            "saveLoadModelConfig",
            "createPredictiveModel",
            "createAndTrainPredictiveModel",
            "trainPredictiveModel",
            "inferPredictiveModel",
            "pollPredictiveModelInference",
            "updateForecast",
            "deleteForecast",
            "getAnomalyHistoryPredictions",
            "deleteAnomalyHistoryPredictions",
            "getFailureModeHistoryAllDevices",
            "getFailureModeHistory",
            "createFailureModeRecord",
            "createFailureModeRecords",
            "updateFailureModeRecord",
            "deleteFailureModeRecord",
            "importFailureModeRecords",
        ],
    ),
)


def build_pandas_agent(settings: Settings) -> BaseAgent:
    name, (text, tool_filter) = PANDAS_DOMAIN
    return LlmAgent(
        name=name,
        model=build_model(settings),
        description=text,
        instruction=build_scoped_instruction(name, text),
        tools=[
            MCPToolset(
                connection_params=SseConnectionParams(
                    url=settings.pandas_mcp_server_url
                ),
                tool_filter=build_scoped_tool_filter(name, tool_filter),
            )
        ],
        before_tool_callback=guard_scoped_tool_calls,
    )


def build_pdm_agent(settings: Settings) -> BaseAgent:
    name, (text, tool_filter) = PDM_DOMAIN
    return LlmAgent(
        name=name,
        model=build_model(settings),
        description=text,
        instruction=build_scoped_instruction(name, text),
        tools=[
            MCPToolset(
                connection_params=SseConnectionParams(url=settings.pdm_mcp_server_url),
                tool_filter=build_scoped_tool_filter(name, tool_filter),
            )
        ],
        before_tool_callback=guard_scoped_tool_calls,
    )


# ── AssetOpsBench domain sub-agents ─────────────────────────────────────────
# These agents connect to FastMCP servers from the assetopsbench submodule,
# running as SSE services in Docker.  Each agent is scoped to its domain's
# tools via MCPToolset's tool_filter.

WO_DOMAIN: tuple[str, tuple[str, list[str]]] = (
    "wo_agent",
    (
        "Manages work order lifecycle for industrial assets: list, get, create, "
        "approve, assign technicians, close, and cancel work orders. Also provides "
        "KPIs, cost breakdowns, schedule calendars, and actuals-vs-planned analysis. "
        "Backed by CouchDB with Maximo-style field names.",
        [
            "list_workorders",
            "get_workorder",
            "get_workorder_tasks",
            "get_workorder_costs",
            "get_workorder_actuals_vs_planned",
            "get_workorder_kpis",
            "get_schedule_calendar",
            "get_my_assigned_workorders",
            "generate_work_order",
            "update_workorder",
            "approve_workorder",
            "assign_technician",
            "close_workorder",
            "cancel_workorder",
        ],
    ),
)

TSFM_DOMAIN: tuple[str, tuple[str, list[str]]] = (
    "tsfm_agent",
    (
        "Runs time-series foundation model (IBM Granite TinyTimeMixer) workflows: "
        "zero-shot forecasting, few-shot fine-tuning, conformal anomaly detection, "
        "and integrated forecasting+anomaly detection. Use for predictive analytics "
        "on sensor telemetry data.",
        [
            "get_ai_tasks",
            "get_tsfm_models",
            "run_tsfm_forecasting",
            "run_tsfm_finetuning",
            "run_tsad",
            "run_integrated_tsad",
        ],
    ),
)

FMSR_DOMAIN: tuple[str, tuple[str, list[str]]] = (
    "fmsr_agent",
    (
        "Failure mode and sensor reasoning: get known failure modes for assets "
        "(curated for chillers/AHUs, LLM-generated for others) and determine "
        "which sensors can detect each failure mode via bidirectional FM-sensor "
        "relevancy mapping.",
        [
            "get_failure_modes",
            "get_failure_mode_sensor_mapping",
        ],
    ),
)

IOT_SENSOR_DOMAIN: tuple[str, tuple[str, list[str]]] = (
    "iot_sensor_agent",
    (
        "Browses IoT sensor data and asset registries from CouchDB: list sites, "
        "assets, and sensors; query historical readings; get asset nameplate details; "
        "and compare installed vs streaming sensors. Complements ThingsBoard "
        "telemetry_agent with structured site/asset/sensor hierarchy.",
        [
            "sites",
            "assets",
            "sensors",
            "history",
            "get_asset",
            "asset_sensors",
            "registry_assets",
        ],
    ),
)

VIBRATION_DOMAIN: tuple[str, tuple[str, list[str]]] = (
    "vibration_agent",
    (
        "Vibration signal analysis and rotating machinery fault detection: "
        "FFT spectrum, envelope analysis for bearing faults, ISO 10816 severity "
        "assessment, bearing frequency calculation, and full automated vibration "
        "diagnosis pipeline. Use for predictive maintenance on rotating equipment.",
        [
            "get_vibration_data",
            "list_vibration_sensors",
            "compute_fft_spectrum",
            "compute_envelope_spectrum",
            "assess_vibration_severity",
            "calculate_bearing_frequencies",
            "list_known_bearings",
            "diagnose_vibration",
        ],
    ),
)


def _build_domain_agent(
    domain: tuple[str, tuple[str, list[str]]],
    mcp_url: str,
    settings: Settings,
) -> BaseAgent:
    name, (text, tool_filter) = domain
    return LlmAgent(
        name=name,
        model=build_model(settings),
        description=text,
        instruction=build_scoped_instruction(name, text),
        tools=[
            MCPToolset(
                connection_params=SseConnectionParams(url=mcp_url),
                tool_filter=build_scoped_tool_filter(name, tool_filter),
            )
        ],
        before_tool_callback=guard_scoped_tool_calls,
    )


def build_assetopsbench_agents(settings: Settings) -> list[BaseAgent]:
    return [
        _build_domain_agent(WO_DOMAIN, settings.wo_mcp_server_url, settings),
        _build_domain_agent(TSFM_DOMAIN, settings.tsfm_mcp_server_url, settings),
        _build_domain_agent(FMSR_DOMAIN, settings.fmsr_mcp_server_url, settings),
        _build_domain_agent(IOT_SENSOR_DOMAIN, settings.iot_mcp_server_url, settings),
        _build_domain_agent(VIBRATION_DOMAIN, settings.vibration_mcp_server_url, settings),
    ]
