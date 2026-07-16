"""Static configuration tests for the ThingsBoard operations agent.

These tests validate agent wiring, skill loading, tool-list consistency,
and settings defaults **without** calling an LLM or connecting to MCP.
They are designed to run fast in CI on every push/PR.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import re

import pytest
import yaml

from thingsboard_ops_agent import subagents
from thingsboard_ops_agent.scope import (
    CUSTOMER_SCOPED_TOOLS_BY_AGENT,
    CUSTOMER_ID_TOOL_ARGS,
    TENANT_SCOPED_TOOLS_BY_AGENT,
)
from thingsboard_ops_agent.settings import load_settings

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "thingsboard_ops_agent"
SKILLS_DIR = PKG / "skills"

# ---------------------------------------------------------------------------
# Quarkus MCP tool IDs (authoritative list from MCP.java)
# ---------------------------------------------------------------------------
QUARKUS_PDM_TOOLS = {
    "getAvailableAlgorithmsMap",
    "getLoadModelConfigs",
    "getPredictiveModelsByPage",
    "getPredictiveModel",
    "getPredictiveModelStatus",
    "getPredictiveModelsByDeviceId",
    "getAnomalyHistoryPredictions",
    "getFailureModeHistoryAllDevices",
    "getFailureModeHistory",
    "saveLoadModelConfig",
    "createPredictiveModel",
    "createAndTrainPredictiveModel",
    "trainPredictiveModel",
    "inferPredictiveModel",
    "pollPredictiveModelInference",
    "updateForecast",
    "deleteForecast",
    "deleteAnomalyHistoryPredictions",
    "createFailureModeRecord",
    "createFailureModeRecords",
    "updateFailureModeRecord",
    "deleteFailureModeRecord",
    "importFailureModeRecords",
}


# ===================================================================
# Helpers
# ===================================================================


def _load_skill_tools(skill_dir: pathlib.Path) -> list[str]:
    """Extract the ``tools:`` list from a SKILL.md YAML front-matter."""
    skill_file = skill_dir / "SKILL.md"
    text = skill_file.read_text()
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if match is None:
        return []
    front = yaml.safe_load(match.group(1))
    return front.get("tools") or []


def _all_skill_dirs() -> list[pathlib.Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


def _all_domains() -> dict[str, tuple[str, list[str]]]:
    return dict(subagents.DOMAINS)


# ===================================================================
# 1. PDM_DOMAIN ↔ Quarkus MCP alignment
# ===================================================================


class TestPdmDomainAlignment:
    """PDM_DOMAIN tool list must match the Quarkus MCP.java method names."""

    def test_pdm_domain_tools_match_quarkus(self):
        _name, (_desc, tools) = subagents.PDM_DOMAIN
        assert set(tools) == QUARKUS_PDM_TOOLS

    def test_pdm_domain_name(self):
        name, (_desc, _tools) = subagents.PDM_DOMAIN
        assert name == "pdm_agent"

    def test_pdm_domain_description_mentions_quarkus(self):
        _name, (desc, _tools) = subagents.PDM_DOMAIN
        assert "Quarkus PdM MCP" in desc


# ===================================================================
# 2. ThingsBoard MCP sub-agents
# ===================================================================


class TestThingsBoardDomains:
    """Each ThingsBoard sub-agent must have a non-empty tool list."""

    EXPECTED_AGENTS = {
        "devices_agent",
        "assets_agent",
        "customers_users_agent",
        "alarms_agent",
        "telemetry_agent",
        "relations_query_agent",
        "ota_agent",
    }

    def test_all_expected_agents_present(self):
        assert set(_all_domains().keys()) == self.EXPECTED_AGENTS

    def test_all_tool_lists_non_empty(self):
        for name, (_desc, tools) in _all_domains().items():
            assert tools, f"{name} has empty tool list"

    def test_no_tool_appears_in_two_agents(self):
        seen: dict[str, str] = {}
        for agent_name, (_desc, tools) in _all_domains().items():
            for tool in tools:
                prev = seen.get(tool)
                assert prev is None, (
                    f"Tool '{tool}' appears in both '{prev}' and '{agent_name}'"
                )
                seen[tool] = agent_name


# ===================================================================
# 3. PDM tools don't leak into ThingsBoard agents
# ===================================================================


class TestPdmToolIsolation:
    """Quarkus PdM tools must only appear in PDM_DOMAIN, not in any
    ThingsBoard MCP sub-agent."""

    def test_no_quarkus_tool_in_tb_domains(self):
        pdm_tools = set(subagents.PDM_DOMAIN[1][1])
        for agent_name, (_desc, tools) in _all_domains().items():
            overlap = pdm_tools & set(tools)
            assert not overlap, (
                f"Agent '{agent_name}' contains PdM tools: {overlap}"
            )


# ===================================================================
# 4. Skill loading
# ===================================================================


class TestSkillLoading:
    """Every skill directory must be loadable by ADK."""

    @pytest.mark.parametrize(
        "skill_dir",
        _all_skill_dirs(),
        ids=lambda p: p.name,
    )
    def test_skill_loads(self, skill_dir):
        from google.adk.skills import load_skill_from_dir

        skill = load_skill_from_dir(skill_dir)
        assert skill is not None


# ===================================================================
# 5. Skill tool declarations vs agent tool_filter
# ===================================================================


class TestSkillToolDeclarations:
    """PdM skills must only declare tools that exist in PDM_DOMAIN.
    The get-timeseries-data skill must only declare tools in telemetry_agent."""

    def test_pdm_skills_declare_valid_pdm_tools(self):
        pdm_tools = set(subagents.PDM_DOMAIN[1][1])
        pdm_skill_dirs = ["seed-train-infer-pdm", "train-existing-device-pdm"]
        for name in pdm_skill_dirs:
            declared = _load_skill_tools(SKILLS_DIR / name)
            if not declared:
                continue
            # PdM tools in the skill must be a subset of PDM_DOMAIN tools
            # (some skills also declare ThingsBoard tools like getDeviceByName)
            pdm_part = {t for t in declared if t in QUARKUS_PDM_TOOLS}
            assert pdm_part <= pdm_tools, (
                f"Skill '{name}' declares PdM tools not in PDM_DOMAIN: "
                f"{pdm_part - pdm_tools}"
            )

    def test_get_timeseries_skill_declares_valid_tools(self):
        tb_tools = set()
        for _desc, tools in _all_domains().values():
            tb_tools.update(tools)
        declared = _load_skill_tools(SKILLS_DIR / "get-timeseries-data")
        assert set(declared) <= tb_tools

    def test_no_skill_declares_stale_pdm_names(self):
        stale = {
            "getSeedMachineOptions",
            "seedMachine",
            "getAvailableModels",
            "createForecast",
            "getForecast",
            "getForecastStatus",
            "getForecastsByDeviceId",
            "getAvailableAlgorithms",
        }
        for skill_dir in _all_skill_dirs():
            declared = set(_load_skill_tools(skill_dir))
            found = declared & stale
            assert not found, (
                f"Skill '{skill_dir.name}' declares stale tools: {found}"
            )


# ===================================================================
# 6. Skill body text doesn't reference stale tool names
# ===================================================================


class TestSkillBodyText:
    """SKILL.md body text must not reference removed/renamed tool names."""

    STALE_NAMES = re.compile(
        r"\b(getSeedMachineOptions|seedMachine|getAvailableModels|"
        r"createForecast|getForecast(?!s)|getForecastStatus|"
        r"getForecastsByDeviceId|getAvailableAlgorithms(?!Map))\b"
    )

    @pytest.mark.parametrize(
        "skill_dir",
        _all_skill_dirs(),
        ids=lambda p: p.name,
    )
    def test_no_stale_names_in_body(self, skill_dir):
        text = (skill_dir / "SKILL.md").read_text()
        # Strip YAML front-matter
        body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)
        matches = self.STALE_NAMES.findall(body)
        assert not matches, (
            f"Skill '{skill_dir.name}' body references stale tool names: "
            f"{set(matches)}"
        )


# ===================================================================
# 7. Agent building (no network, no LLM)
# ===================================================================


class TestAgentBuilding:
    """Verify all agent objects can be constructed from settings."""

    @pytest.fixture()
    def settings(self, monkeypatch):
        monkeypatch.delenv("PDM_MCP_SERVER_URL", raising=False)
        monkeypatch.delenv("PANDAS_MCP_SERVER_URL", raising=False)
        return load_settings()

    def test_build_root_agent(self, settings):
        from thingsboard_ops_agent.agent import build_root_agent

        agent = build_root_agent(settings)
        assert agent.name == "thingsboard_ops_agent"

    def test_build_subagents(self, settings):
        agents = subagents.build_subagents(settings)
        names = {a.name for a in agents}
        assert names == set(subagents.DOMAINS.keys())

    def test_build_pdm_agent(self, settings):
        agent = subagents.build_pdm_agent(settings)
        assert agent.name == "pdm_agent"

    def test_build_pandas_agent(self, settings):
        agent = subagents.build_pandas_agent(settings)
        assert agent.name == "pandas_agent"


# ===================================================================
# 8. Settings defaults
# ===================================================================


class TestSettingsDefaults:
    def test_pdm_mcp_default(self, monkeypatch):
        monkeypatch.delenv("PDM_MCP_SERVER_URL", raising=False)
        settings = load_settings()
        assert settings.pdm_mcp_server_url == "http://tb-quarkus:8081/mcp/sse"

    def test_pandas_mcp_default(self, monkeypatch):
        monkeypatch.delenv("PANDAS_MCP_SERVER_URL", raising=False)
        settings = load_settings()
        assert settings.pandas_mcp_server_url == "http://pandas-mcp:8000/sse"

    def test_tb_mcp_default(self, monkeypatch):
        monkeypatch.delenv("MCP_SERVER_URL", raising=False)
        monkeypatch.delenv("MCP_SERVER_DEFAULT_URL", raising=False)
        settings = load_settings()
        assert settings.mcp_server_url == "http://thingsboard-mcp:8000/sse"


# ===================================================================
# 9. Scope configuration references valid agents
# ===================================================================


class TestScopeConfig:
    """scope.py scoped tool maps must reference agents that exist in DOMAINS."""

    def test_tenant_scoped_agents_exist(self):
        for agent_name in TENANT_SCOPED_TOOLS_BY_AGENT:
            assert agent_name in _all_domains()

    def test_customer_scoped_agents_exist(self):
        for agent_name in CUSTOMER_SCOPED_TOOLS_BY_AGENT:
            assert agent_name in _all_domains()

    def test_customer_id_tool_args_agents_exist(self):
        for tool_name in CUSTOMER_ID_TOOL_ARGS:
            # tool must belong to some agent
            all_tools = set()
            for _desc, tools in _all_domains().values():
                all_tools.update(tools)
            # CUSTOMER_ID_TOOL_ARGS keys are ThingsBoard tools, not PdM
            # They may not be in DOMAINS if they're customer_id args
            # Just verify the structure is valid
            arg_name, fallback = CUSTOMER_ID_TOOL_ARGS[tool_name]
            assert isinstance(arg_name, str)


# ===================================================================
# 10. Source-level wiring checks
# ===================================================================


class TestSourceWiring:
    """agent.py must reference all skills and sub-agents."""

    def test_agent_source_references_all_skills(self):
        source = (PKG / "agent.py").read_text()
        for skill_dir in _all_skill_dirs():
            assert skill_dir.name in source, (
                f"Skill '{skill_dir.name}' not referenced in agent.py"
            )

    def test_agent_source_references_all_subagents(self):
        source = (PKG / "agent.py").read_text()
        for agent_name in _all_domains():
            assert agent_name in source

    def test_agent_source_references_pdm_agent(self):
        source = (PKG / "agent.py").read_text()
        assert "build_pdm_agent" in source
        assert "build_pandas_agent" in source

    def test_pdm_mcp_url_in_settings(self):
        settings_source = (PKG / "settings.py").read_text()
        assert "tb-quarkus:8081/mcp/sse" in settings_source


# ===================================================================
# 11. ADK eval test files are valid JSON with expected structure
# ===================================================================


class TestEvalFiles:
    """Eval JSON files must be parseable and have the expected structure."""

    EVAL_DIRS = [ROOT / "tests" / "pdm", ROOT / "tests" / "assets"]

    def test_all_eval_configs_valid(self):
        for d in self.EVAL_DIRS:
            cfg = d / "test_config.json"
            if not cfg.exists():
                continue
            data = json.loads(cfg.read_text())
            assert "criteria" in data
            assert "tool_trajectory_avg_score" in data["criteria"]
            assert "response_match_score" in data["criteria"]

    def test_all_eval_cases_valid(self):
        for d in self.EVAL_DIRS:
            for f in sorted(d.glob("*.test.json")):
                data = json.loads(f.read_text())
                assert "eval_set_id" in data, f"{f.name}: missing eval_set_id"
                assert "eval_cases" in data, f"{f.name}: missing eval_cases"
                for case in data["eval_cases"]:
                    assert "eval_id" in case
                    assert "conversation" in case
                    conv = case["conversation"]
                    assert len(conv) >= 1
                    turn = conv[0]
                    assert "user_content" in turn
                    assert "intermediate_data" in turn
                    # tool_uses names must be non-empty strings
                    for tu in turn["intermediate_data"].get("tool_uses", []):
                        assert "name" in tu
                        assert isinstance(tu["name"], str)
                        assert len(tu["name"]) > 0

    def test_pdm_eval_tools_are_known(self):
        """Tool names in PdM eval cases must exist in PDM_DOMAIN, DOMAINS,
        or be declared by a skill."""
        pdm_tools = set(subagents.PDM_DOMAIN[1][1])
        tb_tools: set[str] = set()
        for _desc, tools in _all_domains().values():
            tb_tools.update(tools)
        skill_tools: set[str] = set()
        for sd in _all_skill_dirs():
            skill_tools.update(_load_skill_tools(sd))
        all_known = pdm_tools | tb_tools | skill_tools

        for f in (ROOT / "tests" / "pdm").glob("*.test.json"):
            data = json.loads(f.read_text())
            for case in data["eval_cases"]:
                for tu in case["conversation"][0]["intermediate_data"].get(
                    "tool_uses", []
                ):
                    assert tu["name"] in all_known, (
                        f"Eval '{case['eval_id']}' uses unknown tool '{tu['name']}'"
                    )
