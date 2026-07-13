from pathlib import Path

from shared.settings import load_settings
from thingsboard_ops_agent import subagents


ROOT = Path(__file__).resolve().parents[1]


def test_pdm_agent_domain_includes_seed_train_infer_tools():
    name, (description, tools) = subagents.PDM_DOMAIN

    assert name == "pdm_agent"
    assert "Quarkus PdM MCP" in description
    assert "seedMachine" in tools
    assert "createForecast" in tools
    assert "createAndTrainPredictiveModel" in tools
    assert "trainPredictiveModel" in tools
    assert "inferPredictiveModel" in tools
    assert "pollPredictiveModelInference" in tools
    assert "getAnomalyHistoryPredictions" in tools


def test_seed_train_infer_skill_is_registered_in_root_agent_source():
    agent_source = (ROOT / "thingsboard_ops_agent" / "agent.py").read_text()
    skill_path = (
        ROOT
        / "thingsboard_ops_agent"
        / "skills"
        / "seed-train-infer-pdm"
        / "SKILL.md"
    )
    skill_source = skill_path.read_text()

    assert "seed-train-infer-pdm" in agent_source
    assert "build_pdm_agent" in agent_source
    assert "tb-quarkus:8081/mcp/sse" in (
        ROOT / "shared" / "settings.py"
    ).read_text()
    assert "trainPredictiveModel" in skill_source
    assert "pollPredictiveModelInference" in skill_source
    assert "api-specs/openapi.yaml" not in skill_source


def test_pdm_mcp_server_url_has_default(monkeypatch):
    monkeypatch.delenv("PDM_MCP_SERVER_URL", raising=False)

    settings = load_settings()

    assert settings.pdm_mcp_server_url == "http://tb-quarkus:8081/mcp/sse"
