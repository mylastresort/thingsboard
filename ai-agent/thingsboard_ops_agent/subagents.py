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

from shared.settings import Settings
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
        "endpoint. Use it to seed a new machine, create/update model configs, "
        "train models, start inference, poll model/job status, and fetch "
        "forecast or anomaly prediction history.",
        [
            "getSeedMachineOptions",
            "seedMachine",
            # "getAvailableModels",
            "createForecast",
            "createPredictiveModel",
            "createAndTrainPredictiveModel",
            "trainPredictiveModel",
            "inferPredictiveModel",
            "pollPredictiveModelInference",
            "updateForecast",
            "getForecast",
            "getForecastStatus",
            "getForecastsByDeviceId",
            "getAnomalyHistoryPredictions",
            "deleteAnomalyHistoryPredictions",
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
