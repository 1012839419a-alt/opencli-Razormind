"""Registered-Agent adapter for the local Codex CLI.

The adapter is deliberately an edge-side subprocess adapter.  The control
plane sends an ``agent_task`` over the authenticated Agent transport; only the
registered Agent process imports this module and starts ``codex``.  No shell is
used and no provider credential is copied into readiness or runtime events.

Codex ``exec --json`` emits JSONL.  The native protocol has changed names a few
times, so translation accepts the stable ``thread.*``, ``turn.*`` and
``item.*`` envelopes while keeping our event envelope closed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from backend.agent_runtimes.base import (
    AgentTask,
    RuntimeAdapter,
    RuntimeCapabilities,
    RuntimeReadiness,
    event_done,
    event_error,
    event_started,
    event_state,
    event_text,
    event_tool_call,
    event_tool_result,
)
from backend.agent_runtimes.registry import register_runtime

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 1800
_MAX_TIMEOUT_SECONDS = 3600
_VERSION_TIMEOUT_SECONDS = 5
_KILL_GRACE_SECONDS = 10
_STDERR_TAIL_BYTES = 2048
_PERMISSION_MODES = frozenset({"approval_required", "full_auto", "read_only", "suggest_changes"})
_SANDBOX_MODES = frozenset({"read-only", "workspace-write", "danger-full-access"})
_VERSION_RE = re.compile(r"\bcodex(?:[- ]cli)?(?:\s+version)?\s+([0-9][0-9A-Za-z.+-]*)\b", re.I)
_BARE_VERSION_RE = re.compile(r"\b([0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[-+][0-9A-Za-z.-]+)?)\b")


@register_runtime
class CodexRuntimeAdapter(RuntimeAdapter):
    """Run ``codex exec --json`` on a registered local Agent node."""

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
        binary = config.get("binary", "codex")
        if not isinstance(binary, str) or not binary.strip():
            errors.append("'binary' must be a non-empty string")
        elif "\x00" in binary:
            errors.append("'binary' must not contain NUL bytes")

        for key in ("cwd", "project_root"):
            if key in config and config[key] is not None:
                value = config[key]
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"'{key}' must be a non-empty string when provided")
                elif "\x00" in value:
                    errors.append(f"'{key}' must not contain NUL bytes")

        if "args" in config and config["args"] is not None:
            args = config["args"]
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                errors.append("'args' must be a list of strings when provided")

        permission_mode = config.get("permission_mode")
        if permission_mode is not None and permission_mode not in _PERMISSION_MODES:
            errors.append(
                "'permission_mode' must be one of " + ", ".join(sorted(_PERMISSION_MODES))
            )
        sandbox_mode = config.get("sandbox_mode")
        if sandbox_mode is not None and sandbox_mode not in _SANDBOX_MODES:
            errors.append("'sandbox_mode' must be one of " + ", ".join(sorted(_SANDBOX_MODES)))
        if "model" in config and config["model"] is not None:
            if not isinstance(config["model"], str) or not config["model"].strip():
                errors.append("'model' must be a non-empty string when provided")

        if "timeout_seconds" in config and config["timeout_seconds"] is not None:
            timeout = config["timeout_seconds"]
            if (
                not isinstance(timeout, (int, float))
                or isinstance(timeout, bool)
                or not 0 < timeout <= _MAX_TIMEOUT_SECONDS
            ):
                errors.append(
                    f"'timeout_seconds' must be between 0 and {_MAX_TIMEOUT_SECONDS} when provided"
                )
        return errors

    async def health(self) -> bool:
        return self.is_available()

    @classmethod
    def is_available(cls, binary: str = "codex") -> bool:
        """Cheap check used by the Agent registration handshake."""
        if not isinstance(binary, str) or not binary or "\x00" in binary:
            return False
        return shutil.which(binary) is not None

    async def readiness(self, config: dict[str, Any] | None = None) -> RuntimeReadiness:
        config = config or {}
        errors = self.validate_config(config)
        if errors:
            return RuntimeReadiness(
                runtime=self.runtime_type,
                status="blocked",
                binary_present=False,
                reason_code="invalid_config",
                reason="; ".join(errors),
            )

        binary = config.get("binary") or "codex"
        resolved_binary = shutil.which(binary)
        if resolved_binary is None:
            return RuntimeReadiness(
                runtime=self.runtime_type,
                status="blocked",
                binary_present=False,
                reason_code="missing_binary",
                reason=f"codex binary not found: {binary!r}",
            )

        try:
            project_root, cwd = self._resolve_paths(config)
        except ValueError as exc:
            return RuntimeReadiness(
                runtime=self.runtime_type,
                status="blocked",
                binary_present=True,
                permitted_project_root=self._display_path(config.get("project_root")),
                working_directory=self._display_path(config.get("cwd")),
                reason_code="invalid_path",
                reason=str(exc),
            )

        version = await self._detect_version(
            resolved_binary, config.get("args") or [], timeout_seconds=_VERSION_TIMEOUT_SECONDS
        )
        return RuntimeReadiness(
            runtime=self.runtime_type,
            status="ready",
            binary_present=True,
            version=version,
            permitted_project_root=str(project_root),
            working_directory=str(cwd),
        )

    def _compose_argv(self, config: dict[str, Any], prompt: str = "") -> list[str]:
        binary = config.get("binary") or "codex"
        argv = [binary, *(config.get("args") or []), "exec", "--json", "--color", "never"]
        permission_mode = config.get("permission_mode")
        if permission_mode == "full_auto":
            # Codex exposes automatic review, not the old generic approval flag.
            # Keep the sandbox bounded; the dangerous bypass flag is never
            # selected by the Agent runtime.
            argv.extend(("--approve-for-me", "--sandbox", "workspace-write"))
        elif permission_mode == "read_only":
            argv.extend(("--sandbox", "read-only"))
        elif permission_mode in {"suggest_changes", "approval_required"}:
            # Default Codex approval flow is the governed on-request mode.
            pass

        sandbox_mode = config.get("sandbox_mode")
        if sandbox_mode is not None and permission_mode not in {"read_only", "full_auto"}:
            argv.extend(("--sandbox", sandbox_mode))
        model = config.get("model")
        if model:
            argv.extend(("--model", model))
        argv.append(prompt)
        return argv

    def _compose_prompt(self, task: AgentTask) -> str:
        payload = task.input if isinstance(task.input, dict) else {}
        message = payload.get("message") or payload.get("prompt") or ""
        if not isinstance(message, str):
            message = str(message)
        if task.instructions:
            return f"{task.instructions}\n\n{message}".strip()
        return message

    async def invoke(self, task: AgentTask) -> AsyncIterator[dict[str, Any]]:
        config = task.config or {}
        config_errors = self.validate_config(config)
        if config_errors:
            yield event_error(task.task_id, "; ".join(config_errors), error_type="ConfigError")
            return

        binary = config.get("binary") or "codex"
        resolved_binary = shutil.which(binary)
        if resolved_binary is None:
            yield event_error(
                task.task_id,
                f"codex binary not found: {binary!r}",
                error_type="FileNotFoundError",
            )
            return
        try:
            _project_root, cwd = self._resolve_paths(config)
        except ValueError as exc:
            yield event_error(task.task_id, str(exc), error_type="PathError")
            return

        timeout_seconds = config.get("timeout_seconds") or _DEFAULT_TIMEOUT_SECONDS
        version = await self._detect_version(
            resolved_binary,
            config.get("args") or [],
            timeout_seconds=min(timeout_seconds, _VERSION_TIMEOUT_SECONDS),
        )
        argv = self._compose_argv(config, self._compose_prompt(task))

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
        except FileNotFoundError as exc:
            yield event_error(task.task_id, f"codex binary not found: {binary!r}", type(exc).__name__)
            return
        except OSError as exc:
            yield event_error(task.task_id, f"failed to spawn codex: {exc}", type(exc).__name__)
            return

        yield event_started(task.task_id)
        yield event_state(
            task.task_id,
            {"runtime": self.runtime_type, "codex_version": version, "working_directory": str(cwd)},
        )

        accumulated_text: list[str] = []
        native_error: str | None = None

        async def _read_events() -> AsyncIterator[dict[str, Any]]:
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                stripped = line.decode(errors="replace").strip("\r\n")
                if not stripped:
                    continue
                try:
                    native = json.loads(stripped)
                except json.JSONDecodeError:
                    logger.debug("codex_adapter: skipping non-JSON stdout line: %r", stripped[:200])
                    continue
                if not isinstance(native, dict):
                    continue
                translated = self._translate_event(task.task_id, native)
                if translated is not None:
                    yield translated

        try:
            async with asyncio.timeout(timeout_seconds):
                async for event in _read_events():
                    if event["type"] == "text":
                        accumulated_text.append(event.get("text", ""))
                    elif event["type"] == "error":
                        native_error = event.get("message") or "Codex reported an error"
                        break
                    yield event
        except (TimeoutError, asyncio.CancelledError) as exc:
            await self._stop_process(proc)
            if isinstance(exc, asyncio.CancelledError):
                raise
            yield event_error(
                task.task_id,
                f"codex run timed out after {timeout_seconds}s",
                error_type="TimeoutError",
            )
            return

        returncode = await proc.wait()
        if native_error is not None:
            yield event_error(task.task_id, native_error, error_type="RuntimeInvocationError")
            return
        if returncode != 0:
            stderr_tail = b""
            if proc.stderr is not None:
                stderr_tail = await proc.stderr.read()
            tail = stderr_tail[-_STDERR_TAIL_BYTES:].decode(errors="replace")
            detail = f": {tail}" if tail else ""
            yield event_error(
                task.task_id,
                f"codex exited with code {returncode}{detail}",
                error_type="ProcessExitError",
            )
            return

        yield event_done(
            task.task_id,
            result={
                "runtime": self.runtime_type,
                "codex_version": version,
                "exit_code": returncode,
                "text": "".join(accumulated_text),
            },
        )

    async def _detect_version(
        self,
        binary: str,
        args: list[str] | None = None,
        timeout_seconds: float = _VERSION_TIMEOUT_SECONDS,
    ) -> str | None:
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                *(args or []),
                "--version",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            return None
        except OSError:
            return None
        except asyncio.CancelledError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        line = stdout.decode(errors="replace").splitlines()[0].strip() if stdout else ""
        match = _VERSION_RE.search(line) or _BARE_VERSION_RE.search(line)
        return match.group(0) if match else None

    async def _stop_process(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=_KILL_GRACE_SECONDS)
        except TimeoutError:
            proc.kill()
            await proc.wait()

    def _resolve_paths(self, config: dict[str, Any]) -> tuple[Path, Path]:
        project_root_raw = config.get("project_root") or config.get("cwd") or str(Path.cwd())
        cwd_raw = config.get("cwd") or project_root_raw
        project_root = Path(project_root_raw).expanduser().resolve()
        cwd = Path(cwd_raw).expanduser().resolve()
        if not project_root.is_dir():
            raise ValueError(f"permitted project root is not a directory: {project_root}")
        if not cwd.is_dir():
            raise ValueError(f"working directory is not a directory: {cwd}")
        try:
            cwd.relative_to(project_root)
        except ValueError as exc:
            raise ValueError(
                f"working directory {cwd} is outside permitted project root {project_root}"
            ) from exc
        return project_root, cwd

    @staticmethod
    def _display_path(value: object) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        return str(Path(value).expanduser().resolve())

    def _translate_event(self, task_id: str, native: dict[str, Any]) -> dict[str, Any] | None:
        native_type = native.get("type")
        if native_type in {"error", "turn.error"}:
            return event_error(task_id, str(native.get("message") or native.get("error") or "Codex error"))
        if native_type == "thread.started":
            return event_state(task_id, {"thread_id": native.get("thread_id")})
        if native_type == "turn.started":
            return event_state(task_id, {"turn": "started"})
        if native_type == "turn.completed":
            state: dict[str, Any] = {"turn": "completed"}
            if isinstance(native.get("usage"), dict):
                state["usage"] = native["usage"]
            return event_state(task_id, state)

        item = native.get("item") if isinstance(native.get("item"), dict) else native
        item_type = item.get("type")
        if item_type in {"agent_message", "assistant_message", "text"}:
            text = item.get("text") or item.get("content") or native.get("text")
            return event_text(task_id, text) if isinstance(text, str) and text else None
        if item_type in {"command_execution", "tool_call", "function_call"}:
            if native_type in {"item.completed", "tool_result", "function_result"}:
                output = item.get("aggregated_output", item.get("output", item.get("result")))
                exit_code = item.get("exit_code")
                return event_tool_result(
                    task_id,
                    name=str(item.get("command") or item.get("name") or "codex_tool"),
                    result=output,
                    call_id=item.get("id") or item.get("call_id"),
                    is_error=bool(item.get("is_error")) or exit_code not in (None, 0),
                )
            return event_tool_call(
                task_id,
                name=str(item.get("command") or item.get("name") or "codex_tool"),
                args=item.get("arguments") if isinstance(item.get("arguments"), dict) else {"command": item.get("command", "")},
                call_id=item.get("id") or item.get("call_id"),
            )
        if native_type in {"text", "output_text.delta", "response.output_text.delta"}:
            text = native.get("text") or native.get("delta")
            return event_text(task_id, text) if isinstance(text, str) and text else None
        logger.debug("codex_adapter: skipping unmapped native event type %r", native_type)
        return None
