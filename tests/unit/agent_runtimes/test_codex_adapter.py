"""Focused contract tests for the registered-Agent Codex runtime adapter."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.agent_runtimes.base import AgentTask
from backend.agent_runtimes.codex_adapter import CodexRuntimeAdapter
from backend.agent_runtimes.registry import get_runtime, list_runtime_types


class _CompletedProcess:
    def __init__(self, lines: list[dict] | None = None, *, returncode: int = 0, stderr: bytes = b""):
        import json

        self.returncode = returncode
        self.stdout = asyncio.StreamReader()
        for line in lines or []:
            self.stdout.feed_data((json.dumps(line) + "\n").encode())
        self.stdout.feed_eof()
        self.stderr = asyncio.StreamReader()
        if stderr:
            self.stderr.feed_data(stderr)
        self.stderr.feed_eof()

    async def wait(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9


class _HangingProcess:
    def __init__(self):
        self.returncode = None
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()

    async def wait(self) -> int:
        return -15 if self.returncode is None else self.returncode

    def terminate(self) -> None:
        self.returncode = -15
        self.stdout.feed_eof()
        self.stderr.feed_eof()

    def kill(self) -> None:
        self.returncode = -9
        self.stdout.feed_eof()
        self.stderr.feed_eof()


def _task(tmp_path: Path, **config) -> AgentTask:
    return AgentTask(
        task_id="task-1",
        workflow="exec",
        instructions="Inspect the repository.",
        input={"message": "Report the result."},
        config={"cwd": str(tmp_path), **config},
    )


def test_codex_json_events_become_closed_runtime_events():
    adapter = CodexRuntimeAdapter()

    call = adapter._translate_event(
        "task-1",
        {
            "type": "item.started",
            "item": {"id": "cmd-1", "type": "command_execution", "command": "python verify.py"},
        },
    )
    result = adapter._translate_event(
        "task-1",
        {
            "type": "item.completed",
            "item": {
                "id": "cmd-1",
                "type": "command_execution",
                "command": "python verify.py",
                "aggregated_output": "",
                "exit_code": 0,
            },
        },
    )
    final_text = adapter._translate_event(
        "task-1",
        {"type": "item.completed", "item": {"type": "agent_message", "text": "{\"tests\": []}"}},
    )

    assert call == {
        "type": "tool_call",
        "task_id": "task-1",
        "name": "python verify.py",
        "args": {"command": "python verify.py"},
        "call_id": "cmd-1",
    }
    assert result == {
        "type": "tool_result",
        "task_id": "task-1",
        "name": "python verify.py",
        "result": "",
        "call_id": "cmd-1",
        "is_error": False,
    }
    assert final_text == {"type": "text", "task_id": "task-1", "text": "{\"tests\": []}"}


def test_adapter_requires_controller_owned_worktree_and_rejects_launch_overrides(tmp_path):
    adapter = CodexRuntimeAdapter()

    assert adapter.validate_config({"timeout_seconds": 10}) == [
        "'cwd' must be a non-empty controller-owned worktree path"
    ]
    errors = adapter.validate_config(
        {
            "cwd": str(tmp_path),
            "binary": "python",
            "args": ["payload.py"],
            "project_root": str(tmp_path),
            "sandbox_mode": "danger-full-access",
        }
    )
    assert errors == [
        "unsupported controller runtime config: args, binary, project_root, sandbox_mode"
    ]


@pytest.mark.parametrize("permission_mode", ["observe_only", "suggest_changes", None])
def test_advisory_profiles_always_use_ephemeral_read_only_sandbox(tmp_path, permission_mode):
    adapter = CodexRuntimeAdapter()
    config = {"cwd": str(tmp_path)}
    if permission_mode is not None:
        config["permission_mode"] = permission_mode
    assert adapter.validate_config(config) == []

    argv = adapter._compose_argv("codex", tmp_path.resolve(), "Inspect")
    assert argv == [
        "codex",
        "exec",
        "--json",
        "--color",
        "never",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--cd",
        str(tmp_path.resolve()),
        "Inspect",
    ]
    assert "--approve-for-me" not in argv
    assert "danger-full-access" not in argv


@pytest.mark.parametrize("permission_mode", ["low_risk_automatic", "full_auto", "read_only"])
def test_unpublished_permission_modes_are_rejected(tmp_path, permission_mode):
    errors = CodexRuntimeAdapter().validate_config(
        {"cwd": str(tmp_path), "permission_mode": permission_mode}
    )
    assert errors == [
        "'permission_mode' must be one of observe_only, suggest_changes"
    ]


async def test_readiness_reports_fixed_binary_version_and_confined_path(monkeypatch, tmp_path):
    adapter = CodexRuntimeAdapter()
    monkeypatch.setattr(
        "backend.agent_runtimes.codex_adapter.shutil.which",
        lambda name: "C:/tools/codex.exe" if name == "codex" else None,
    )
    monkeypatch.setattr(adapter, "_detect_version", AsyncMock(return_value="codex-cli 1.2.3"))

    readiness = await adapter.readiness({"cwd": str(tmp_path)})

    assert readiness.status == "ready"
    assert readiness.runtime == "codex"
    assert readiness.binary_present is True
    assert readiness.version == "codex-cli 1.2.3"
    assert readiness.permitted_project_root == str(tmp_path.resolve())
    assert readiness.working_directory == str(tmp_path.resolve())
    assert not hasattr(readiness, "api_key")


async def test_readiness_blocks_missing_or_invalid_worktree(monkeypatch, tmp_path):
    adapter = CodexRuntimeAdapter()
    monkeypatch.setattr(
        "backend.agent_runtimes.codex_adapter.shutil.which",
        lambda _name: "C:/tools/codex.exe",
    )

    missing_config = await adapter.readiness({})
    invalid_path = await adapter.readiness({"cwd": str(tmp_path / "missing")})

    assert missing_config.status == "blocked"
    assert missing_config.reason_code == "invalid_config"
    assert missing_config.binary_present is True
    assert invalid_path.status == "blocked"
    assert invalid_path.reason_code == "invalid_path"


async def test_missing_binary_is_terminal_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.agent_runtimes.codex_adapter.shutil.which",
        lambda _name: None,
    )

    events = [
        event
        async for event in CodexRuntimeAdapter().invoke(_task(tmp_path))
    ]

    assert events == [
        {
            "type": "error",
            "task_id": "task-1",
            "message": "codex binary not found",
            "error_type": "FileNotFoundError",
        }
    ]


async def test_version_probe_uses_only_fixed_binary(monkeypatch):
    captured: list[tuple] = []

    class VersionProcess:
        returncode = 0

        async def communicate(self):
            return b"codex-cli 1.2.3\n", b""

    async def spawn(*argv, **kwargs):
        captured.append(argv)
        return VersionProcess()

    monkeypatch.setattr(
        "backend.agent_runtimes.codex_adapter.asyncio.create_subprocess_exec",
        spawn,
    )

    version = await CodexRuntimeAdapter()._detect_version("C:/tools/codex.exe")

    assert version == "codex-cli 1.2.3"
    assert captured == [("C:/tools/codex.exe", "--version")]


async def test_event_normalization_and_terminal_result(monkeypatch, tmp_path):
    adapter = CodexRuntimeAdapter()
    process = _CompletedProcess(
        [
            {"type": "thread.started", "thread_id": "thread-1"},
            {
                "type": "item.started",
                "item": {
                    "id": "call-1",
                    "type": "command_execution",
                    "command": "git status",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "call-1",
                    "type": "command_execution",
                    "command": "git status",
                    "aggregated_output": "clean",
                    "exit_code": 0,
                },
            },
            {"type": "item.completed", "item": {"type": "agent_message", "text": "hello"}},
            {"type": "turn.completed", "usage": {"input_tokens": 1}},
        ]
    )
    captured: dict = {}

    async def spawn(*argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setattr(
        "backend.agent_runtimes.codex_adapter.shutil.which",
        lambda name: "C:/tools/codex.exe" if name == "codex" else None,
    )
    monkeypatch.setattr(
        "backend.agent_runtimes.codex_adapter.asyncio.create_subprocess_exec",
        spawn,
    )
    monkeypatch.setattr(adapter, "_detect_version", AsyncMock(return_value="codex-cli 1.2.3"))

    events = [event async for event in adapter.invoke(_task(tmp_path))]

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
    assert events[1]["state"] == {"runtime": "codex", "codex_version": "codex-cli 1.2.3"}
    assert "working_directory" not in events[1]["state"]
    assert events[-1]["result"] == {
        "runtime": "codex",
        "codex_version": "codex-cli 1.2.3",
        "exit_code": 0,
        "text": "hello",
    }
    assert captured["kwargs"]["cwd"] == str(tmp_path.resolve())
    assert captured["argv"][0] == "C:/tools/codex.exe"
    assert "--ephemeral" in captured["argv"]
    assert sum(event["type"] in {"done", "error"} for event in events) == 1


async def test_timeout_stops_process_and_yields_typed_error(monkeypatch, tmp_path):
    adapter = CodexRuntimeAdapter()
    process = _HangingProcess()

    async def spawn(*_argv, **_kwargs):
        return process

    monkeypatch.setattr(
        "backend.agent_runtimes.codex_adapter.shutil.which",
        lambda _name: "C:/tools/codex.exe",
    )
    monkeypatch.setattr(
        "backend.agent_runtimes.codex_adapter.asyncio.create_subprocess_exec",
        spawn,
    )
    monkeypatch.setattr(adapter, "_detect_version", AsyncMock(return_value="codex-cli 1.2.3"))

    events = [
        event
        async for event in adapter.invoke(_task(tmp_path, timeout_seconds=0.01))
    ]

    assert process.returncode == -15
    assert events[-1]["type"] == "error"
    assert events[-1]["error_type"] == "TimeoutError"
    assert sum(event["type"] in {"done", "error"} for event in events) == 1


def test_codex_registered():
    assert "codex" in list_runtime_types()
    assert get_runtime("codex").runtime_type == "codex"
