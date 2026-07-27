"""ThingsBoard session scope helpers for the operations agent."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from .settings import Settings
import re

AUTHORITY_KEY = "tb:authority"
CUSTOMER_ID_KEY = "tb:customer_id"
TENANT_ID_KEY = "tb:tenant_id"
SCOPE_RESOLVED_KEY = "tb:scope_resolved"

UNKNOWN_AUTHORITY = "UNKNOWN"
CUSTOMER_USER = "CUSTOMER_USER"

NULL_UUID = "13814000-1dd2-11b2-8080-808080808080"

CUSTOMER_SCOPED_DEVICE_TOOLS = {
    "getCustomerDevices",
    "getDeviceById",
    "getDevicesByIds",
    "getDeviceCredentialsByDeviceId",
}

TENANT_SCOPED_DEVICE_TOOLS = {
    "createOrUpsertDevice",
    "deleteDevice",
    "getDeviceById",
    "getDeviceCredentialsByDeviceId",
    "getDevicesByIds",
    "getTenantDevice",
    "getTenantDevices",
    "saveDevice",
}

TENANT_SCOPED_TOOLS_BY_AGENT = {
    "devices_agent": TENANT_SCOPED_DEVICE_TOOLS,
    "assets_agent": {
        "deleteAsset",
        "getAssetById",
        "getTenantAsset",
        "getTenantAssets",
        "saveAsset",
    },
}

CUSTOMER_SCOPED_TOOLS_BY_AGENT = {
    "devices_agent": CUSTOMER_SCOPED_DEVICE_TOOLS,
    "assets_agent": {
        "getAssetById",
        "getCustomerAssets",
    },
    "customers_users_agent": {
        "getCustomerById",
        "getCustomerUsers",
        "getUserById",
        "getUsers",
    },
    "alarms_agent": {
        "getAlarmInfoById",
        "getAlarmTypes",
        "getAlarms",
        "getAllAlarms",
        "getHighestAlarmSeverity",
    },
    "telemetry_agent": {
        "getAttributeKeys",
        "getAttributeKeysByScope",
        "getAttributes",
        "getAttributesByScope",
        "getLatestTimeseries",
        "getTimeseries",
        "getTimeseriesKeys",
    },
    "relations_query_agent": {
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
        "findByFromWithRelationType",
        "findByToWithRelationType",
        "findEntityDataByApiUsageStateFilter",
        "findEntityDataByAssetSearchQueryFilter",
        "findEntityDataByAssetTypeFilter",
        "findEntityDataByDeviceSearchQueryFilter",
        "findEntityDataByDeviceTypeFilter",
        "findEntityDataByEdgeQueryFilter",
        "findEntityDataByEntityGroupFilter",
        "findEntityDataByEntityGroupListFilter",
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
        "getEntityGroupsByIds",
        "getEntityGroupsByType",
        "getEntityGroupsForEntity",
        "getKeyFiltersGuide",
        "getRelation",
    },
    "ota_agent": {
        "countByDeviceProfileAndEmptyOtaPackage",
        "downloadOtaPackage",
        "getOtaPackageById",
        "getOtaPackageInfoById",
        "getOtaPackages",
        "getOtaPackagesByDeviceProfile",
    },
}

# Flat merged sets for the single thingsboard_agent (O(1) lookups).
TENANT_SCOPED_TOOLS: set[str] | None = None
for _agent_tools in TENANT_SCOPED_TOOLS_BY_AGENT.values():
    if TENANT_SCOPED_TOOLS is None:
        TENANT_SCOPED_TOOLS = set(_agent_tools)
    else:
        TENANT_SCOPED_TOOLS |= _agent_tools

CUSTOMER_SCOPED_TOOLS: set[str] | None = None
for _agent_tools in CUSTOMER_SCOPED_TOOLS_BY_AGENT.values():
    if CUSTOMER_SCOPED_TOOLS is None:
        CUSTOMER_SCOPED_TOOLS = set(_agent_tools)
    else:
        CUSTOMER_SCOPED_TOOLS |= _agent_tools

CUSTOMER_ID_TOOL_ARGS = {
    "getCustomerAssets": ("customerId", "getTenantAssets"),
    "getCustomerDevices": ("customerId", "getTenantDevices"),
    "getCustomerUsers": ("customerId", "getUsers"),
    "getCustomerById": ("customerId", None),
}

KNOWN_IDS_KEY = "tb:known_ids"
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def harvest_known_ids(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext, tool_response: Any
) -> None:
    known = set(tool_context.state.get(KNOWN_IDS_KEY, []))
    payload = tool_response if isinstance(tool_response, str) else str(tool_response)
    known.update(_UUID_RE.findall(payload))
    tool_context.state[KNOWN_IDS_KEY] = list(known)


def guard_id_provenance(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> dict[str, Any] | None:
    """before_tool_callback: *Id args must trace back to a prior tool result
    or the session's fixed customer/tenant id — never an LLM guess."""
    known = set(tool_context.state.get(KNOWN_IDS_KEY, set()))
    known |= {
        tool_context.state.get(CUSTOMER_ID_KEY),
        tool_context.state.get(TENANT_ID_KEY),
    }
    known.discard(None)

    for key, val in args.items():
        if not key.lower().endswith("id") or not isinstance(val, str):
            continue
        if not _UUID_RE.fullmatch(val) or val == NULL_UUID:
            continue  # not UUID-shaped, or handled elsewhere
        if val not in known:
            return {
                "error": (
                    f"{key}='{val}' was never returned by a lookup tool in "
                    "this session. Do not guess ids — call the matching "
                    "list/search tool first and reuse the id it returns."
                )
            }
    return None


def guard_tool_call(tool, args, tool_context):
    return guard_scoped_tool_calls(tool, args, tool_context) or guard_id_provenance(
        tool, args, tool_context
    )


def build_scope_resolver(settings: Settings) -> Callable[[CallbackContext], Any]:
    async def resolve_tb_scope(callback_context: CallbackContext) -> None:
        state = callback_context.state
        if state.get(SCOPE_RESOLVED_KEY):
            return
        state[SCOPE_RESOLVED_KEY] = True
        state[AUTHORITY_KEY] = settings.tb_authority
        state[CUSTOMER_ID_KEY] = settings.tb_customer_id
        state[TENANT_ID_KEY] = settings.tb_tenant_id

    return resolve_tb_scope


def build_scoped_instruction(
    agent_name: str, base_text: str
) -> Callable[[ReadonlyContext], str]:
    def scoped_instruction(ctx: ReadonlyContext) -> str:
        authority = ctx.state.get(AUTHORITY_KEY, UNKNOWN_AUTHORITY)
        customer_id = ctx.state.get(CUSTOMER_ID_KEY)

        guard_prompt = (
            "Never invent an id, count, or attribute value. If a tool errors or "
            "returns nothing, say so or call a lookup tool — do not retry with a "
            "different guessed value, and do not answer from what a similar entity "
            "'probably' has."
        )

        if authority == CUSTOMER_USER:
            if agent_name == "thingsboard_agent":
                scope_text = (
                    f"This session is scoped to customer {customer_id}. Use "
                    f"customer-scoped tools with customerId='{customer_id}'; "
                    "tenant-wide mutation/admin operations are not valid here. "
                    "Never ask for or guess a customer id."
                )
            elif agent_name == "devices_agent":
                scope_text = (
                    f"This session is scoped to customer {customer_id}. Use "
                    f"getCustomerDevices with customerId='{customer_id}' and "
                    "never ask for or guess a customer id, because it is "
                    "already fixed by the session. getTenantDevices and "
                    "getTenantDevice are not valid for this session."
                )
            elif agent_name == "assets_agent":
                scope_text = (
                    f"This session is scoped to customer {customer_id}. Use "
                    f"getCustomerAssets with customerId='{customer_id}' for "
                    "asset lists and getAssetById for known visible asset ids. "
                    "getTenantAssets and getTenantAsset are not valid for this "
                    "session."
                )
            elif agent_name == "customers_users_agent":
                scope_text = (
                    f"This session is scoped to customer {customer_id}. Use "
                    f"getCustomerById/getCustomerUsers with customerId="
                    f"'{customer_id}', or getUsers for users visible to the "
                    "current caller. Tenant-wide customer/admin tools are not "
                    "valid for this session."
                )
            else:
                scope_text = (
                    f"This session is scoped to customer {customer_id}. Only "
                    "use tools that operate on entities visible to this current "
                    "customer session; tenant-wide mutation/admin operations "
                    "are not valid here."
                )
            return f"{base_text} {scope_text} Only use the tools you've been given. {guard_prompt}"

        scope_text = (
            "This session is tenant/sysadmin-scoped or scope could not be "
            "resolved. Use tenant/current-user scope tools by default. Only use "
            "customer-specific tools after obtaining a real customer id from a "
            "customer lookup, and never derive one from an asset/entity "
            f"customerId field because {NULL_UUID} is ThingsBoard's "
            "null-customer sentinel."
        )
        return f"{base_text} {scope_text} Only use the tools you've been given. {guard_prompt}"

    return scoped_instruction


def build_devices_instruction(base_text: str) -> Callable[[ReadonlyContext], str]:
    return build_scoped_instruction("devices_agent", base_text)


def build_scoped_tool_filter(
    agent_name: str, base_tool_filter: list[str]
) -> Callable[[BaseTool, ReadonlyContext | None], bool]:
    base_tools = set(base_tool_filter)

    def scoped_tool_filter(tool: BaseTool, ctx: ReadonlyContext | None = None) -> bool:
        if tool.name not in base_tools:
            return False

        authority = (
            ctx.state.get(AUTHORITY_KEY, UNKNOWN_AUTHORITY)
            if ctx is not None
            else UNKNOWN_AUTHORITY
        )
        if authority == CUSTOMER_USER:
            allowed = CUSTOMER_SCOPED_TOOLS_BY_AGENT.get(agent_name)
        else:
            allowed = TENANT_SCOPED_TOOLS_BY_AGENT.get(agent_name)

        if allowed is None:
            return True
        return tool.name in allowed

    return scoped_tool_filter


def guard_scoped_tool_calls(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> dict[str, Any] | None:
    customer_tool = CUSTOMER_ID_TOOL_ARGS.get(tool.name)
    if customer_tool is None:
        return None

    arg_name, tenant_fallback_tool = customer_tool
    customer_id = args.get(arg_name)
    cached_customer_id = tool_context.state.get(CUSTOMER_ID_KEY)

    if cached_customer_id and (not customer_id or customer_id == NULL_UUID):
        args[arg_name] = cached_customer_id
        return None

    if cached_customer_id and customer_id != cached_customer_id:
        return {
            "error": (
                f"Session is scoped to customer {cached_customer_id}; refusing "
                f"to query a different customerId ({customer_id})."
            )
        }

    if customer_id == NULL_UUID or not customer_id:
        fallback = (
            f" Use {tenant_fallback_tool} instead."
            if tenant_fallback_tool
            else " Provide a real customerId from a customer lookup."
        )
        return {
            "error": (
                "customerId is ThingsBoard's null-customer sentinel or missing; "
                "this asset/entity has no real customer."
                f"{fallback}"
            )
        }

    return None


def guard_device_calls(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> dict[str, Any] | None:
    return guard_scoped_tool_calls(tool, args, tool_context)
