import pytest
from pydantic import ValidationError

from backend.schemas.operations_agent import (
    DEFAULT_DEEP_RUN_TIMEOUT_SECONDS,
    MAX_DEEP_RUN_TIMEOUT_SECONDS,
    AgentRuntimeBindingV1,
)


def _binding(**overrides):
    values = {
        "schema_version": "agent.runtime-binding.v1",
        "agent_url": "https://agent.example.test",
        "runtime": "pi",
        "workflow": "operations-agent",
    }
    values.update(overrides)
    return values


def test_deep_run_timeout_defaults_are_bounded():
    binding = AgentRuntimeBindingV1.model_validate(_binding())

    assert binding.dispatch_timeout_seconds == DEFAULT_DEEP_RUN_TIMEOUT_SECONDS == 1800
    assert MAX_DEEP_RUN_TIMEOUT_SECONDS == 3600


def test_codex_and_existing_runtimes_are_valid_bindings():
    for runtime in ("miniflow", "pi", "codex"):
        binding = AgentRuntimeBindingV1.model_validate(_binding(runtime=runtime))
        assert binding.runtime == runtime


def test_dispatch_timeout_enforces_hard_bounds():
    with pytest.raises(ValidationError):
        AgentRuntimeBindingV1.model_validate(
            _binding(dispatch_timeout_seconds=MAX_DEEP_RUN_TIMEOUT_SECONDS + 1)
        )
    with pytest.raises(ValidationError):
        AgentRuntimeBindingV1.model_validate(_binding(dispatch_timeout_seconds=0))


def test_inner_timeout_override_enforces_same_hard_bounds():
    with pytest.raises(ValidationError):
        AgentRuntimeBindingV1.model_validate(
            _binding(config={"timeout_seconds": MAX_DEEP_RUN_TIMEOUT_SECONDS + 1})
        )
    with pytest.raises(ValidationError):
        AgentRuntimeBindingV1.model_validate(_binding(config={"timeout_seconds": 0}))
