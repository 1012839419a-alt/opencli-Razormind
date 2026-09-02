"""Prime Agent adapter using its documented pi-compatible JSONL RPC mode."""

from backend.agent_runtimes.base import RuntimeCapabilities
from backend.agent_runtimes.pi_adapter import PiRuntimeAdapter
from backend.agent_runtimes.registry import register_runtime


@register_runtime
class PrimeAgentRuntimeAdapter(PiRuntimeAdapter):
    """Run ``prime-agent --mode rpc`` without moving provider secrets off-node."""

    runtime_type = "prime-agent"
    binary_name = "prime-agent"
    session_dir_env = "PRIME_AGENT_SESSION_DIR"
    capabilities = RuntimeCapabilities(
        transport="stdio",
        streaming=True,
        resume_by_id=False,
        checkpoint="none",
        concurrent_sessions=True,
        features=frozenset(
            {
                "agent_messaging",
                "heartbeats",
                "model_selection",
                "schedules",
                "subagents",
                "tool_events",
                "workspace_read",
                "workspace_write",
            }
        ),
    )
