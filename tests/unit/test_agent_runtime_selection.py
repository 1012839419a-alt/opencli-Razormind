import pytest

from backend.models.edge_node import EdgeNode
from backend.schemas.operations_agent import AgentContractV2, AgentRuntimeBindingV2
from backend.services import agent_runtime_selection


def _contract(*capabilities: str) -> AgentContractV2:
    return AgentContractV2.model_validate(
        {
            "schema_version": "agent.contract.v2",
            "role": "sales_researcher",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "state_schema": {"type": "object"},
            "required_capabilities": list(capabilities),
            "tool_policy": {},
            "budget": {},
            "quality_gates": [],
            "evidence_requirements": [],
        }
    )


def _binding(**overrides) -> AgentRuntimeBindingV2:
    value = {
        "schema_version": "agent.runtime-binding.v2",
        "workflow": "sales-agent",
        "preferred_agent_urls": [],
        "preferred_runtimes": ["codex"],
        "model_binding": None,
        "config": {},
    }
    value.update(overrides)
    return AgentRuntimeBindingV2.model_validate(value)


async def test_selector_uses_capabilities_before_runtime_preference(db_session, monkeypatch):
    node = EdgeNode(
        url="http://capability-agent:19823",
        label="Capability node",
        protocol="ws",
        mode="cdp",
        node_type="docker",
        status="online",
        runtimes=["codex", "prime-agent"],
        runtime_capabilities={
            "codex": ["streaming", "workspace_read"],
            "prime-agent": ["streaming", "subagents", "workspace_read"],
        },
    )
    db_session.add(node)
    await db_session.commit()
    monkeypatch.setattr(
        agent_runtime_selection.ws_agent_manager,
        "is_connected",
        lambda url: url == node.url,
    )

    selected = await agent_runtime_selection.select_agent_runtime(
        db_session,
        contract=_contract("streaming", "subagents"),
        binding=_binding(),
    )

    assert selected["runtime"] == "prime-agent"
    assert selected["capabilities"] == ["streaming", "subagents", "workspace_read"]


async def test_model_binding_requires_model_selection_capability(db_session, monkeypatch):
    node = EdgeNode(
        url="http://model-agent:19823",
        label="Model node",
        protocol="ws",
        mode="cdp",
        node_type="docker",
        status="online",
        runtimes=["codex", "prime-agent"],
        runtime_capabilities={
            "codex": ["streaming"],
            "prime-agent": ["model_selection", "streaming"],
        },
    )
    db_session.add(node)
    await db_session.commit()
    monkeypatch.setattr(
        agent_runtime_selection.ws_agent_manager,
        "is_connected",
        lambda _url: True,
    )
    binding = _binding(
        model_binding={
            "schema_version": "agent.model-binding.v1",
            "provider": "openrouter",
            "model": "anthropic/claude-sonnet",
            "auth_profile": "sales",
        }
    )

    selected = await agent_runtime_selection.select_agent_runtime(
        db_session,
        contract=_contract("streaming"),
        binding=binding,
    )

    assert selected["runtime"] == "prime-agent"
    assert selected["provider"] == "openrouter"
    assert selected["model"] == "anthropic/claude-sonnet"
    assert "auth_profile" in selected


async def test_selector_fails_closed_without_capability_match(db_session, monkeypatch):
    node = EdgeNode(
        url="http://read-only-agent:19823",
        label="Read-only node",
        protocol="ws",
        mode="cdp",
        node_type="docker",
        status="online",
        runtimes=["codex"],
        runtime_capabilities={"codex": ["streaming", "workspace_read"]},
    )
    db_session.add(node)
    await db_session.commit()
    monkeypatch.setattr(
        agent_runtime_selection.ws_agent_manager,
        "is_connected",
        lambda _url: True,
    )

    with pytest.raises(
        agent_runtime_selection.RuntimeSelectionError,
        match="workspace_write",
    ):
        await agent_runtime_selection.select_agent_runtime(
            db_session,
            contract=_contract("workspace_write"),
            binding=_binding(),
        )
