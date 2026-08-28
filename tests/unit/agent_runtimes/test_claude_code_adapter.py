"""Focused contract tests for the local Claude Code runtime adapter."""

import sys
from typing import Any

from backend.agent_runtimes.base import AgentTask
from backend.agent_runtimes.claude_code_adapter import ClaudeCodeRuntimeAdapter
from backend.agent_runtimes.registry import get_runtime, list_runtime_types

_FAKE_CLAUDE = r"""
import json
import sys

if "--version" in sys.argv:
    print("2.1.231 (Claude Code)", flush=True)
    raise SystemExit(0)

def emit(value):
    print(json.dumps(value), flush=True)

emit({"type": "system", "subtype": "init", "model": "test-model", "cwd": "."})
emit({"type": "assistant", "message": {"content": [{
    "type": "tool_use", "id": "tool-1", "name": "Bash",
    "input": {"command": "opencli browser"}
}]}})
emit({"type": "user", "message": {"content": [{
    "type": "tool_result", "tool_use_id": "tool-1", "content": "ok"
}]}})
emit({"type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]}})
emit({"type": "result", "is_error": False, "result": "hello"})
"""


def _write_fake(tmp_path, source: str) -> str:
    path = tmp_path / "fake_claude.py"
    path.write_text(source, encoding="utf-8")
    return str(path)


def _config(script: str, **overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"binary": sys.executable, "args": [script]}
    result.update(overrides)
    return result


def test_compose_argv_uses_claude_stream_protocol(tmp_path):
    argv = ClaudeCodeRuntimeAdapter()._compose_argv(
        {"binary": "claude", "permission_mode": "full_auto", "chrome": True},
        "collect the answer",
        model="sonnet",
    )

    assert argv[:7] == [
        "claude",
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--permission-mode",
    ]
    assert "auto" in argv
    assert "--chrome" in argv
    assert argv[-2:] == ["--model", "sonnet"] or argv[-1] == "collect the answer"


async def test_event_normalization_and_terminal_result(tmp_path):
    script = _write_fake(tmp_path, _FAKE_CLAUDE)
    events = [
        event
        async for event in ClaudeCodeRuntimeAdapter().invoke(
            AgentTask(
                task_id="happy",
                workflow="exec",
                input={"message": "say hello"},
                config=_config(script, cwd=str(tmp_path), project_root=str(tmp_path)),
            )
        )
    ]

    assert [event["type"] for event in events] == [
        "started",
        "state",
        "state",
        "tool_call",
        "tool_result",
        "text",
        "done",
    ]
    assert events[-1]["result"]["text"] == "hello"


def test_claude_code_registered():
    assert "claude-code" in list_runtime_types()
    assert get_runtime("claude-code").runtime_type == "claude-code"
