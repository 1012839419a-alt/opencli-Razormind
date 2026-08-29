"""Subprocess adapter for the installed ``codex exec --json`` CLI."""

import asyncio
import json
import logging
import shutil
from collections.abc import AsyncIterator
from typing import Any

from backend.agent_runtimes.base import (
    AgentTask,
    RuntimeAdapter,
    RuntimeCapabilities,
    event_done,
    event_error,
    event_started,
    event_text,
    event_tool_call,
    event_tool_result,
)
from backend.agent_runtimes.registry import register_runtime

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 600
_KILL_GRACE_SECONDS = 10
_STDERR_TAIL_BYTES = 2_048


@register_runtime
class CodexRuntimeAdapter(RuntimeAdapter):
    """Run Codex with a controller-owned worktree as its writable sandbox."""

    runtime_type = "codex"
    capabilities = RuntimeCapabilities(
        transport="stdio",
        streaming=True,
        resume_by_id=False,
        checkpoint="none",
        concurrent_sessions=True,
    )

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        cwd = config.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            errors.append("'cwd' must be a non-empty controller-owned worktree path")
        timeout = config.get("timeout_seconds")
        if timeout is not None and (
            not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0
        ):
            errors.append("'timeout_seconds' must be a positive number when provided")
        unsupported = sorted(set(config) - {"cwd", "timeout_seconds"})
        if unsupported:
            errors.append("unsupported controller runtime config: " + ", ".join(unsupported))
        return errors

    async def health(self) -> bool:
        return self.is_available()

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("codex") is not None

    @staticmethod
    def _prompt(task: AgentTask) -> str:
        message = task.input.get("message") if isinstance(task.input, dict) else ""
        if not isinstance(message, str):
            message = ""
        return f"{task.instructions}\n\n{message}".strip()

    async def invoke(self, task: AgentTask) -> AsyncIterator[dict[str, Any]]:
        config = task.config or {}
        config_errors = self.validate_config(config)
        if config_errors:
            yield event_error(task.task_id, "; ".join(config_errors), error_type="ConfigError")
            return

        binary = shutil.which("codex")
        if binary is None:
            yield event_error(
                task.task_id, "Codex binary not found", error_type="FileNotFoundError"
            )
            return
        timeout_seconds = config.get("timeout_seconds") or _DEFAULT_TIMEOUT_SECONDS
        proc = await asyncio.create_subprocess_exec(
            binary,
            "exec",
            "--json",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
            "--cd",
            config["cwd"],
            self._prompt(task),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None
        stderr_task = asyncio.create_task(proc.stderr.read())
        accumulated_text: list[str] = []
        terminal_error: str | None = None
        yield event_started(task.task_id)

        try:
            async with asyncio.timeout(timeout_seconds):
                while line := await proc.stdout.readline():
                    try:
                        native = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("codex_adapter: skipping non-JSON stdout line: %r", line[:200])
                        continue
                    translated = self._translate_event(task.task_id, native)
                    if translated is None:
                        continue
                    if translated["type"] == "text":
                        accumulated_text.append(translated["text"])
                    elif translated["type"] == "error":
                        terminal_error = translated["message"]
                        break
                    yield translated
        except (TimeoutError, asyncio.CancelledError) as exc:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=_KILL_GRACE_SECONDS)
            except TimeoutError:
                proc.kill()
                await proc.wait()
            if isinstance(exc, asyncio.CancelledError):
                raise
            yield event_error(
                task.task_id,
                f"Codex run timed out after {timeout_seconds}s",
                error_type="TimeoutError",
            )
            return

        returncode = await proc.wait()
        stderr = await stderr_task
        if terminal_error is not None:
            yield event_error(task.task_id, terminal_error, error_type="RuntimeInvocationError")
            return
        if returncode != 0:
            tail = stderr[-_STDERR_TAIL_BYTES:].decode(errors="replace")
            yield event_error(
                task.task_id,
                f"Codex exited with code {returncode}: {tail}",
                error_type="ProcessExitError",
            )
            return
        yield event_done(task.task_id, result={"text": "".join(accumulated_text)})

    def _translate_event(self, task_id: str, native: dict[str, Any]) -> dict[str, Any] | None:
        native_type = native.get("type")
        raw_item = native.get("item")
        item: dict[str, Any] = raw_item if isinstance(raw_item, dict) else {}
        item_type = item.get("type")

        if native_type == "item.started" and item_type == "command_execution":
            return event_tool_call(
                task_id,
                name="command_execution",
                args={"command": item.get("command", "")},
                call_id=item.get("id"),
            )
        if native_type == "item.completed" and item_type == "command_execution":
            return event_tool_result(
                task_id,
                name="command_execution",
                result=item.get("aggregated_output", ""),
                call_id=item.get("id"),
                is_error=item.get("exit_code") not in {None, 0},
            )
        if native_type == "item.completed" and item_type == "agent_message":
            return event_text(task_id, item.get("text", ""))
        if native_type == "error":
            message = native.get("message") or native.get("error") or "Codex reported an error"
            return event_error(task_id, str(message))
        return None
