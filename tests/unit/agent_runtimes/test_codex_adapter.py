"""Focused contract tests for the registered-Agent Codex runtime adapter."""

import asyncio
import sys
from typing import Any

import pytest

from backend.agent_runtimes.base import AgentTask
from backend.agent_runtimes.codex_adapter import CodexRuntimeAdapter
from backend.agent_runtimes.registry import get_runtime, list_runtime_types

_FAKE_CODEX = r'''
import json
import sys
import time

if "--version" in sys.argv:
    print("codex-cli 1.2.3", flush=True)
    raise SystemExit(0)

def emit(value):
    print(json.dumps(value), flush=True)

emit({"type": "thread.started", "thread_id": "thread-1"})
emit({"type": "item.started", "item": {"id": "call-1", "type": "command_execution", "command": "ls"}})
emit({"type": "item.completed", "item": {"id": "call-1", "type": "command_execution", "command": "ls", "aggregated_output": "README", "exit_code": 0}})
emit({"type": "item.completed", "item": {"type": "agent_message", "text": "hello"}})
emit({"type": "turn.completed", "usage": {"input_tokens": 1}})
'''

_FAKE_CODEX_HANG = r'''
import sys
import time
if "--version" in sys.argv:
    print("codex-cli 1.2.3", flush=True)
    raise SystemExit(0)
time.sleep(30)
'''


def _write_fake(tmp_path, source: str) -> str:
    path = tmp_path / "fake_codex.py"
    path.write_text(source, encoding="utf-8")
    return str(path)


def _config(script: str, **overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "binary": sys.executable,
        "args": [script],
    }
    result.update(overrides)
    return result


async def test_missing_binary_is_terminal_error():
    events = [
        event
        async for event in CodexRuntimeAdapter().invoke(
            AgentTask(task_id="missing", workflow="exec", config={"binary": "not-a-codex-binary"})
        )
    ]
    assert events == [
        {
            "type": "error",
            "task_id": "missing",
            "message": "codex binary not found: 'not-a-codex-binary'",
            "error_type": "FileNotFoundError",
        }
    ]


async def test_readiness_reports_version_and_confined_paths(tmp_path):
    script = _write_fake(tmp_path, _FAKE_CODEX)
    readiness = await CodexRuntimeAdapter().readiness(
        _config(script, project_root=str(tmp_path), cwd=str(tmp_path))
    )
    assert readiness.status == "ready"
    assert readiness.runtime == "codex"
    assert readiness.binary_present is True
    assert readiness.version == "codex-cli 1.2.3"
    assert readiness.permitted_project_root == str(tmp_path.resolve())
    assert readiness.working_directory == str(tmp_path.resolve())
    assert not hasattr(readiness, "api_key")


def test_validate_config_accepts_registered_agent_config(tmp_path):
    errors = CodexRuntimeAdapter().validate_config(
        {
            "binary": "codex",
            "project_root": str(tmp_path),
            "cwd": str(tmp_path),
            "timeout_seconds": 120,
            "permission_mode": "approval_required",
        }
    )
    assert errors == []


async def test_invalid_working_directory_is_blocked(tmp_path):
    outside = tmp_path / "outside"
    readiness = await CodexRuntimeAdapter().readiness(
        {
            "binary": sys.executable,
            "project_root": str(tmp_path),
            "cwd": str(outside),
        }
    )
    assert readiness.status == "blocked"
    assert readiness.reason_code == "invalid_path"


async def test_event_normalization_and_terminal_result(tmp_path):
    script = _write_fake(tmp_path, _FAKE_CODEX)
    events = [
        event
        async for event in CodexRuntimeAdapter().invoke(
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
        "state",
        "done",
    ]
    assert events[-1]["result"]["text"] == "hello"
    assert events[-1]["result"]["codex_version"] == "codex-cli 1.2.3"
    assert sum(event["type"] in {"done", "error"} for event in events) == 1


async def test_timeout_stops_process_and_yields_typed_error(tmp_path):
    script = _write_fake(tmp_path, _FAKE_CODEX_HANG)
    events = [
        event
        async for event in CodexRuntimeAdapter().invoke(
            AgentTask(
                task_id="timeout",
                workflow="exec",
                config=_config(
                    script,
                    cwd=str(tmp_path),
                    project_root=str(tmp_path),
                    timeout_seconds=0.1,
                ),
            )
        )
    ]
    assert events[-1]["type"] == "error"
    assert events[-1]["error_type"] == "TimeoutError"
    assert sum(event["type"] in {"done", "error"} for event in events) == 1


async def test_cancellation_stops_process(tmp_path):
    script = _write_fake(tmp_path, _FAKE_CODEX_HANG)
    adapter = CodexRuntimeAdapter()
    task = AgentTask(
        task_id="cancel",
        workflow="exec",
        config=_config(script, cwd=str(tmp_path), project_root=str(tmp_path), timeout_seconds=30),
    )
    started = asyncio.Event()

    async def consume():
        async for event in adapter.invoke(task):
            if event["type"] == "started":
                started.set()

    consumer = asyncio.create_task(consume())
    await started.wait()
    consumer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(consumer, timeout=1)


def test_codex_registered():
    assert "codex" in list_runtime_types()
    assert get_runtime("codex").runtime_type == "codex"
