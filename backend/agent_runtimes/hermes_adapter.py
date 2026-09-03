"""Subprocess adapter for Hermes Agent's one-shot ``-z`` mode."""

from __future__ import annotations

import asyncio
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


@register_runtime
class HermesRuntimeAdapter(RuntimeAdapter):
    """Run Hermes Agent as ``hermes [-m model] -z prompt``."""

    runtime_type = "hermes"
    capabilities = RuntimeCapabilities(
        transport="stdio",
        streaming=False,
        resume_by_id=False,
        checkpoint="none",
        concurrent_sessions=True,
        # Hermes can select a requested model/provider, but does not expose
        # policy, budget, quality-gate, or tool events through this transport.
        features=frozenset({"model_selection"}),
    )

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = validate_common_config(config, default_binary="hermes")
        for key in ("model", "provider", "usage_file"):
            if key in config and config[key] is not None and not isinstance(config[key], str):
                errors.append(f"'{key}' must be a string when provided")
        return errors

    async def health(self) -> bool:
        return self.is_available()

    @classmethod
    def is_available(cls, binary: str = "hermes") -> bool:
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
        binary = config.get("binary") or "hermes"
        resolved_binary = shutil.which(binary)
        if resolved_binary is None:
            return RuntimeReadiness(
                runtime=self.runtime_type,
                capability_id=f"runtime.{self.runtime_type}",
                status="blocked",
                binary_present=False,
                reason_code="missing_binary",
                reason=f"Hermes binary not found: {binary!r}",
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
        binary = config.get("binary") or "hermes"
        argv = [binary, *(config.get("args") or [])]
        model = model if model is not None else config.get("model")
        provider = provider if provider is not None else config.get("provider")
        if model:
            argv.extend(["-m", model])
        if provider:
            argv.extend(["--provider", provider])
        usage_file = config.get("usage_file")
        if usage_file:
            argv.extend(["--usage-file", usage_file])
        argv.extend(["-z", message])
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

    async def invoke(self, task: AgentTask) -> AsyncIterator[dict[str, Any]]:
        config = task.config or {}
        config_errors = self.validate_config(config)
        if config_errors:
            yield event_error(task.task_id, "; ".join(config_errors), error_type="ConfigError")
            return

        argv = self._compose_argv(
            config,
            self._compose_message(task),
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
                f"hermes binary not found: {argv[0]!r}",
                error_type=type(exc).__name__,
            )
            return
        except OSError as exc:
            yield event_error(
                task.task_id,
                f"failed to spawn hermes: {exc}",
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
                f"hermes run timed out after {timeout_seconds}s",
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

        text = stdout_bytes.decode(errors="replace").strip()
        if proc.returncode != 0:
            tail = stderr_bytes[-_STDERR_TAIL_BYTES:].decode(errors="replace")
            yield event_error(
                task.task_id,
                f"hermes exited with code {proc.returncode}: {tail}",
                error_type="ProcessExitError",
            )
            return
        if text:
            yield event_text(task.task_id, text)
        yield event_done(task.task_id, result={"text": text})
