from backend.agent_runtimes.base import AgentTask
from backend.agent_runtimes.prime_agent_adapter import PrimeAgentRuntimeAdapter
from backend.agent_runtimes.registry import get_runtime


def test_prime_agent_is_registered_as_distinct_runtime():
    adapter = get_runtime("prime-agent")

    assert isinstance(adapter, PrimeAgentRuntimeAdapter)
    assert adapter.binary_name == "prime-agent"
    assert "subagents" in adapter.capabilities.names()
    assert "model_selection" in adapter.capabilities.names()


def test_prime_agent_rpc_argv_keeps_provider_and_model_separate():
    adapter = PrimeAgentRuntimeAdapter()

    argv = adapter._compose_argv(
        {},
        provider="openrouter",
        model="anthropic/claude-sonnet",
    )

    assert argv == [
        "prime-agent",
        "--provider",
        "openrouter",
        "--model",
        "anthropic/claude-sonnet",
        "--mode",
        "rpc",
    ]


def test_prime_agent_uses_runtime_neutral_prompt_contract():
    adapter = PrimeAgentRuntimeAdapter()
    task = AgentTask(
        task_id="sales-run",
        workflow="sales-agent",
        instructions="Act as a sales researcher",
        input={"prompt": "Research product demand"},
        provider="openrouter",
        model="anthropic/claude-sonnet",
        required_capabilities=("streaming", "subagents"),
    )

    assert adapter._compose_request(task) == {
        "type": "prompt",
        "id": "sales-run",
        "message": "Act as a sales researcher\n\nResearch product demand",
    }
