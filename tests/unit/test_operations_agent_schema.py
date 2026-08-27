import pytest
from pydantic import ValidationError

from backend.schemas.operations_agent import (
    DEFAULT_DEEP_RUN_TIMEOUT_SECONDS,
    MAX_DEEP_RUN_TIMEOUT_SECONDS,
    AgentModelBindingV1,
    AgentRuntimeBindingV2,
)


def _binding(**overrides):
    values = {
        "schema_version": "agent.runtime-binding.v2",
        "preferred_agent_urls": ["https://agent.example.test"],
        "preferred_runtimes": ["pi"],
        "workflow": "operations-agent",
    }
    values.update(overrides)
    return values


def test_deep_run_timeout_defaults_are_bounded():
    binding = AgentRuntimeBindingV2.model_validate(_binding())

    assert binding.dispatch_timeout_seconds == DEFAULT_DEEP_RUN_TIMEOUT_SECONDS == 1800
    assert MAX_DEEP_RUN_TIMEOUT_SECONDS == 3600


def test_runtime_preferences_accept_prime_agent_without_binding_business_role():
    binding = AgentRuntimeBindingV2.model_validate(
        _binding(preferred_runtimes=["prime-agent", "codex"])
    )
    assert binding.preferred_runtimes == ["prime-agent", "codex"]


def test_dispatch_timeout_enforces_hard_bounds():
    with pytest.raises(ValidationError):
        AgentRuntimeBindingV2.model_validate(
            _binding(dispatch_timeout_seconds=MAX_DEEP_RUN_TIMEOUT_SECONDS + 1)
        )
    with pytest.raises(ValidationError):
        AgentRuntimeBindingV2.model_validate(_binding(dispatch_timeout_seconds=0))


def test_inner_timeout_override_enforces_same_hard_bounds():
    with pytest.raises(ValidationError):
        AgentRuntimeBindingV2.model_validate(
            _binding(config={"timeout_seconds": MAX_DEEP_RUN_TIMEOUT_SECONDS + 1})
        )
    with pytest.raises(ValidationError):
        AgentRuntimeBindingV2.model_validate(_binding(config={"timeout_seconds": 0}))

def test_model_binding_rejects_control_plane_credentials():
    with pytest.raises(ValidationError):
        AgentModelBindingV1.model_validate(
            {
                "schema_version": "agent.model-binding.v1",
                "provider": "openrouter",
                "model": "anthropic/claude-sonnet",
                "api_key": "must-stay-on-edge",
            }
        )
