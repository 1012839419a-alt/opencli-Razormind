"""Subprocess adapter for OpenClaw's one-shot ``agent`` command."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import AsyncIterator
from typing import Any

from backend.agent_runtimes.base import (
    AgentTask,
    RuntimeAdapter,
    RuntimeCapabilities,
    RuntimeReadiness,
    event_done,
    event_error,
    event_started,
    event_text,
    validate_common_config,
)
from backend.agent_runtimes.registry import register_runtime

_DEFAULT_TIMEOUT_SECONDS = 300
_KILL_GRACE_SECONDS = 10
_STDERR_TAIL_BYTES = 2048
_REPLY_FIELDS = ("text", "reply", "content", "message", "result", "response")


def _extract_reply_text(payload: Any) -> str | None:
    """Extract reply text from the version-varying OpenClaw JSON envelope."""
    if isinstance(payload, str):
        return payload if payload.strip() else None
    if not isinstance(payload, dict):
        return None
    for key in _REPLY_FIELDS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, dict):
            nested = _extract_reply_text(value)
            if nested:
                return nested
    for value in payload.values():
        if isinstance(value, dict):
            nested = _extract_reply_text(value)
            if nested:
                return nested
    return None


@register_runtime
class OpenClawRuntimeAdapter(RuntimeAdapter):
    """Run ``openclaw agent --agent <id> --model <model> -m <prompt>``."""

    runtime_type = "openclaw"
    capabilities = RuntimeCapabilities(
        transport="stdio",
        streaming=False,
        resume_by_id=False,
        checkpoint="none",
        concurrent_sessions=True,
        # The CLI accepts a model override. Policy, budget, quality-gate, and
        # tool-event capabilities are not exposed by this one-shot transport.
        features=frozenset({"model_selection"}),
    )

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = validate_common_config(config, default_binary="openclaw")
        if "agent_id" in config and config["agent_id"] is not None and not isinstance(
            config["agent_id"], str
        ):
            errors.append("'agent_id' must be a string when provided")
        if "model" in config and config["model"] is not None and not isinstance(
            config["model"], str
        ):
            errors.append("'model' must be a string when provided")
        if "local" in config and config["local"] is not None and not isinstance(
            config["local"], bool
        ):
            errors.append("'local' must be a boolean when provided")
        return errors

    async def health(self) -> bool:
        return self.is_available()

    @classmethod
    def is_available(cls, binary: str = "openclaw") -> bool:
        return isinstance(binary, str) and bool(binary) and shutil.which(binary) is not None

    async def readiness(self, config: dict[str, Any] | None = None) -> RuntimeReadiness:
        config = config or {}
        errors = self.validate_config(config)
        if errors:
            return RuntimeReadiness(
                runtime=self.runtime_type,
                capability_id=f"runtime.{self.runtime_type}",
                status="blocked",
                binary_present=False,
                reason_code="invalid_config",
                reason="; ".join(errors),
            )
        binary = config.get("binary") or "openclaw"
        resolved_binary = shutil.which(binary)
        if resolved_binary is None:
            return RuntimeReadiness(
                runtime=self.runtime_type,
                capability_id=f"runtime.{self.runtime_type}",
                status="blocked",
                binary_present=False,
                reason_code="missing_binary",
                reason=f"OpenClaw binary not found: {binary!r}",
            )
        return RuntimeReadiness(
            runtime=self.runtime_type,
            capability_id=f"runtime.{self.runtime_type}",
            status="ready",
            binary_present=True,
            working_directory=config.get("cwd"),
        )

    def _compose_argv(
        self,
        config: dict[str, Any],
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[str]:
        binary = config.get("binary") or "openclaw"
        argv = [binary, *(config.get("args") or []), "agent"]
        agent_id = config.get("agent_id") or "main"
        argv.extend(["--agent", agent_id])
        if config.get("local"):
            argv.append("--local")
        model = model if model is not None else config.get("model")
        if model:
            # OpenClaw uses a fully-qualified provider/model reference rather
            # than a separate --provider option. Preserve already-qualified
            # model IDs and qualify bare IDs from AgentTask.model.
            if provider and "/" not in model:
                model = f"{provider}/{model}"
            argv.extend(["--model", model])
        argv.extend(["-m", message, "--json"])
        return argv

    def _compose_env(self, config: dict[str, Any]) -> dict[str, str] | None:
        extra_env = config.get("env") or {}
        if not extra_env:
            return None
        return {**os.environ, **extra_env}

    @staticmethod
    def _compose_message(task: AgentTask) -> str:
        payload = task.input if isinstance(task.input, dict) else {}
        message = payload.get("message")
        if message is None:
            message = payload.get("prompt")
        if message is None:
            message = ""
        if not isinstance(message, str):
            message = str(message)
        if task.instructions:
            message = f"{task.instructions}\n\n{message}".strip()
        return message

    def _parse_stdout(self, stdout: str) -> tuple[str | None, str | None]:
        """Return ``(reply_text, json_error)`` with plain-text fallback."""
        candidates = [
            line.strip()
            for line in stdout.splitlines()
            if line.strip().startswith(("{", "["))
        ]
        for candidate in reversed(candidates):
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            text = _extract_reply_text(payload)
            if text:
                return text, None
            return None, "OpenClaw JSON reply contained no recognized text field"
        return None, None

    async def invoke(self, task: AgentTask) -> AsyncIterator[dict[str, Any]]:
        config = task.config or {}
        config_errors = self.validate_config(config)
        if config_errors:
            yield event_error(task.task_id, "; ".join(config_errors), error_type="ConfigError")
            return

        message = self._compose_message(task)
        argv = self._compose_argv(
            config,
            message,
            provider=task.provider,
            model=task.model,
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=config.get("cwd"),
                env=self._compose_env(config),
            )
        except FileNotFoundError as exc:
            yield event_error(
                task.task_id,
                f"openclaw binary not found: {argv[0]!r}",
                error_type=type(exc).__name__,
            )
            return
        except OSError as exc:
            yield event_error(
                task.task_id,
                f"failed to spawn openclaw: {exc}",
                error_type=type(exc).__name__,
            )
            return

        yield event_started(task.task_id)
        timeout_seconds = config.get("timeout_seconds") or _DEFAULT_TIMEOUT_SECONDS
        communicate_task = asyncio.create_task(proc.communicate())
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                asyncio.shield(communicate_task), timeout=timeout_seconds
            )
        except TimeoutError:
            proc.terminate()
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    asyncio.shield(communicate_task), timeout=_KILL_GRACE_SECONDS
                )
            except TimeoutError:
                proc.kill()
                stdout_bytes, stderr_bytes = await communicate_task
            yield event_error(
                task.task_id,
                f"openclaw run timed out after {timeout_seconds}s",
                error_type="TimeoutError",
            )
            return
        except asyncio.CancelledError:
            proc.terminate()
            try:
                await asyncio.wait_for(
                    asyncio.shield(communicate_task),
                    timeout=_KILL_GRACE_SECONDS,
                )
            except TimeoutError:
                proc.kill()
                await communicate_task
            raise

        stdout_text = stdout_bytes.decode(errors="replace")
        reply, json_error = self._parse_stdout(stdout_text)
        if proc.returncode != 0:
            tail = stderr_bytes[-_STDERR_TAIL_BYTES:].decode(errors="replace")
            detail = reply or tail or stdout_text.strip()
            yield event_error(
                task.task_id,
                f"openclaw exited with code {proc.returncode}: {detail[:500]}",
                error_type="ProcessExitError",
            )
            return
        if reply is None:
            body = stdout_text.strip()
            if json_error:
                body = f"{json_error}\n{body}"
            if not body:
                yield event_done(task.task_id, result={"text": ""})
                return
            yield event_text(task.task_id, body)
            yield event_done(task.task_id, result={"text": body})
            return
        yield event_text(task.task_id, reply)
        yield event_done(task.task_id, result={"text": reply})
