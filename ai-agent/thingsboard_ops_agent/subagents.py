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

# name -> (description/instruction, tool_filter)
# Grouped from the 98 tools exposed by the ThingsBoard MCP server.
DOMAINS: dict[str, tuple[str, list[str]]] = {
    "devices_agent": (
        "Manages ThingsBoard devices: create/update, delete, look up, fetch "
        "credentials, and count/search devices.",
        [
            "createOrUpsertDevice",
            "deleteDevice",
            "getDeviceById",
            "getDevicesByIds",
            "getTenantDevice",
            "getTenantDevices",
            "getCustomerDevices",
            "getDeviceCredentialsByDeviceId",
            "saveDevice",
            "saveDeviceAttributes",
            "countByDeviceSearchQueryFilter",
            "countByDeviceTypeFilter",
            "countByDeviceProfileAndEmptyOtaPackage",
            "findEntityDataByDeviceSearchQueryFilter",
            "findEntityDataByDeviceTypeFilter",
        ],
    ),
    "assets_agent": (
        "Manages ThingsBoard assets: create/update, delete, look up, and "
        "count/search assets.",
        [
            "saveAsset",
            "deleteAsset",
            "getAssetById",
            "getTenantAsset",
            "getTenantAssets",
            "getCustomerAssets",
            "countByAssetSearchQueryFilter",
            "countByAssetTypeFilter",
            "findEntityDataByAssetSearchQueryFilter",
            "findEntityDataByAssetTypeFilter",
        ],
    ),
    "customers_users_agent": (
        "Manages ThingsBoard customers and users: create/update/delete and list them.",
        [
            "saveCustomer",
            "deleteCustomer",
            "getCustomerById",
            "getCustomers",
            "getTenantCustomer",
            "getCustomerUsers",
            "saveUser",
            "deleteUser",
            "getUserById",
            "getUsers",
            "getTenantAdmins",
            "getUsersForAssign",
        ],
    ),
    "alarms_agent": (
        "Manages ThingsBoard alarms: acknowledge, clear, delete, create/update, "
        "and query alarms, their types and severity.",
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
        "Reads and writes ThingsBoard entity attributes and time-series telemetry.",
        [
            "getAttributes",
            "getAttributesByScope",
            "getAttributeKeys",
            "getAttributeKeysByScope",
            "getLatestTimeseries",
            "getTimeseries",
            "getTimeseriesKeys",
            "saveEntityAttributesV2",
            "saveEntityTelemetry",
            "saveEntityTelemetryWithTTL",
        ],
    ),
    "relations_query_agent": (
        "Manages entity relations, edges, entity views, and generic entity "
        "data queries/counts (EDQ), including the EDQ and key-filter guides.",
        [
            "findByFromWithRelationType",
            "findByToWithRelationType",
            "findInfoByFrom",
            "findInfoByTo",
            "getRelation",
            "saveRelation",
            "deleteRelation",
            "deleteRelations",
            "countByEdgeQueryFilter",
            "countByEdgeTypeFilter",
            "findEntityDataByEdgeQueryFilter",
            "findEntityDataByEdgeTypeFilter",
            "countByEntityViewSearchQueryFilter",
            "countByEntityViewTypeFilter",
            "findEntityDataByEntityViewSearchQueryFilter",
            "findEntityDataByEntityViewTypeFilter",
            "countByApiUsageStateFilter",
            "countByEntityListFilter",
            "countByEntityNameFilter",
            "countByEntityTypeFilter",
            "countByRelationsQueryFilter",
            "countBySingleEntityFilter",
            "findEntityDataByApiUsageStateFilter",
            "findEntityDataByEntityListFilter",
            "findEntityDataByEntityNameFilter",
            "findEntityDataByEntityTypeFilter",
            "findEntityDataByRelationsQueryFilter",
            "findEntityDataBySingleEntityFilter",
            "findEntityDataByStateEntityOwnerFilter",
            "getEdqCountGuide",
            "getEdqGuide",
            "getKeyFiltersGuide",
        ],
    ),
    "ota_agent": (
        "Manages ThingsBoard OTA firmware/software packages: create/update, "
        "delete, download, and assign to devices or device profiles.",
        [
            "assignOtaPackageToDevice",
            "assignOtaPackageToDeviceProfile",
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
            instruction=f"{text} Only use the tools you've been given.",
            tools=[
                MCPToolset(
                    connection_params=SseConnectionParams(url=settings.mcp_server_url),
                    tool_filter=tool_filter,
                )
            ],
        )
        for name, (text, tool_filter) in DOMAINS.items()
    ]
    return agents
