"""ThingsBoard sub-agents and tool registry.

A single ``thingsboard_agent`` wires to the ThingsBoard MCP server with all
tools exposed through one MCPToolset connection (O(1) connection) and uses a
tool-registry dict for O(1) tool-to-domain routing.  The per-domain dicts
(``DOMAINS``) are kept for backward-compatible scope enforcement and tests.

The root agent (see agent.py) delegates to this single agent instead of
choosing among seven sub-agents, cutting the root-level routing from O(n) to
O(1).
"""

from __future__ import annotations

from collections.abc import Callable

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from .settings import Settings
from .scope import (
    build_scoped_instruction,
    build_scoped_tool_filter,
    guard_scoped_tool_calls,
)
from .langfuse import after_model_callback as langfuse_after_model_callback

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


# ---------------------------------------------------------------------------
# O(1) tool registry: tool_name -> domain name
# Built once from DOMAINS so every runtime lookup is a dict.get() call.
# ---------------------------------------------------------------------------
TOOL_REGISTRY: dict[str, str] = {
    tool: domain for domain, (_desc, tools) in DOMAINS.items() for tool in tools
}

# Merged flat list of all ThingsBoard MCP tools (single MCPToolset connection).
TB_ALL_TOOLS: list[str] = list(TOOL_REGISTRY)

# Merged description for the single thingsboard_agent.
TB_DESCRIPTION = (
    "Manages all ThingsBoard entities through a single agent backed by the "
    "ThingsBoard MCP server.  Covers devices, assets, customers, users, "
    "alarms, telemetry, entity relations, entity groups, EDQ queries, and OTA "
    "packages.  Route directly to the right tool — the tool registry maps "
    "every tool name to its domain (devices, assets, customers_users, alarms, "
    "telemetry, relations_query, ota) for O(1) lookups."
)


def build_model(settings: Settings) -> LiteLlm:
    return LiteLlm(
        model=f"ollama_chat/{settings.ollama_model}",
        api_base=settings.ollama_base_url,
        num_ctx=settings.ollama_num_ctx,
    )


def build_subagents(settings: Settings) -> list[BaseAgent]:
    """Build the single thingsboard_agent (returned as a 1-element list for
    backward compatibility with callers that iterate the result)."""
    return [build_tb_agent(settings)]


def _build_flat_scoped_tool_filter(
    base_tools: list[str],
) -> Callable[[BaseTool, ReadonlyContext | None], bool]:
    """O(1) tool filter for the merged thingsboard_agent.

    Uses the flat ``TB_ALL_TOOLS`` set for membership checks and the per-domain
    scope maps for authority-based filtering.  ``base_tools`` is the full flat
    list; it is converted to a set once at construction time.
    """
    from .scope import (
        AUTHORITY_KEY,
        UNKNOWN_AUTHORITY,
        CUSTOMER_USER,
        CUSTOMER_SCOPED_TOOLS,
        TENANT_SCOPED_TOOLS,
    )

    tool_set = set(base_tools)

    def scoped_tool_filter(tool: BaseTool, ctx: ReadonlyContext | None = None) -> bool:
        if tool.name not in tool_set:
            return False

        authority = (
            ctx.state.get(AUTHORITY_KEY, UNKNOWN_AUTHORITY)
            if ctx is not None
            else UNKNOWN_AUTHORITY
        )
        if authority == CUSTOMER_USER:
            allowed = CUSTOMER_SCOPED_TOOLS
        else:
            allowed = TENANT_SCOPED_TOOLS

        if allowed is None:
            return True
        return tool.name in allowed

    return scoped_tool_filter


def build_tb_agent(settings: Settings) -> BaseAgent:
    """Single ThingsBoard agent with all tools via one MCPToolset (O(1))."""
    return LlmAgent(
        name="thingsboard_agent",
        model=build_model(settings),
        description=TB_DESCRIPTION,
        instruction=build_scoped_instruction("thingsboard_agent", TB_DESCRIPTION),
        tools=[
            MCPToolset(
                connection_params=SseConnectionParams(url=settings.mcp_server_url),
                tool_filter=_build_flat_scoped_tool_filter(TB_ALL_TOOLS),
            )
        ],
        before_tool_callback=guard_scoped_tool_calls,
    )


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
        after_model_callback=langfuse_after_model_callback,
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
        after_model_callback=langfuse_after_model_callback,
        tools=[
            MCPToolset(
                connection_params=SseConnectionParams(url=settings.pdm_mcp_server_url),
                tool_filter=build_scoped_tool_filter(name, tool_filter),
            )
        ],
        before_tool_callback=guard_scoped_tool_calls,
    )
