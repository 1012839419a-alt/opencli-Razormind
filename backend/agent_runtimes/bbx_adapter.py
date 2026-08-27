"""Runtime adapter for the Browser Bridge (BBX) CLI."""

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
    RuntimeInvocationError,
    event_done,
    event_error,
    event_started,
    event_tool_call,
    event_tool_result,
)
from backend.agent_runtimes.registry import register_runtime

_DEFAULT_TIMEOUT_SECONDS = 60.0
_LIST_WORKFLOWS = {"tool.list", "tools.list", "list_tools", "bbx_list_tools"}
_CALL_WORKFLOWS = {"tool.call", "tools.call", "call_tool", "bbx_call"}
_HEALTH_WORKFLOWS = {"health", "server.health", "bbx_health"}


@register_runtime
class BbxRuntimeAdapter(RuntimeAdapter):
    """Translate BBX CLI JSON responses into normalized runtime events."""

    runtime_type = "bbx"
    capabilities = RuntimeCapabilities(
        transport="stdio",
        streaming=False,
        resume_by_id=False,
        checkpoint="none",
        concurrent_sessions=True,
        features=frozenset({"browser", "tool_events"}),
    )

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if "binary" in config and config["binary"] is not None:
            binary = config["binary"]
            if not isinstance(binary, str) or not binary.strip():
                errors.append("'binary' must be a non-empty string when provided")
        if "remote" in config and config["remote"] is not None:
            remote = config["remote"]
            if not isinstance(remote, str) or not remote.strip():
                errors.append("'remote' must be a non-empty string when provided")
        if "timeout_seconds" in config and config["timeout_seconds"] is not None:
            timeout = config["timeout_seconds"]
            if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
                errors.append("'timeout_seconds' must be a positive number when provided")
        return errors

    async def health(self) -> bool:
        try:
            result = await self._run_cli(["status"], {})
            return result.get("ok") is True
        except Exception:
            return False

    @classmethod
    def is_available(cls, binary: str = "bbx") -> bool:
        return bool(os.environ.get("BBX_BINARY")) or shutil.which(binary) is not None

    async def invoke(self, task: AgentTask) -> AsyncIterator[dict[str, Any]]:
        errors = self.validate_config(task.config or {})
        if errors:
            yield event_error(task.task_id, "; ".join(errors), error_type="ValueError")
            return

        yield event_started(task.task_id)
        try:
            if task.workflow in _LIST_WORKFLOWS:
                async for event in self._invoke_list_tools(task):
                    yield event
                return
            if task.workflow in _HEALTH_WORKFLOWS:
                async for event in self._invoke_health(task):
                    yield event
                return
            async for event in self._invoke_call_tool(task):
                yield event
        except RuntimeInvocationError as exc:
            yield event_error(
                task.task_id,
                str(exc),
                error_type=exc.error_type or type(exc).__name__,
            )
        except TimeoutError as exc:
            yield event_error(task.task_id, f"BBX request timed out: {exc}", type(exc).__name__)
        except Exception as exc:
            yield event_error(task.task_id, f"BBX adapter failed: {exc}", type(exc).__name__)

    async def _invoke_list_tools(self, task: AgentTask) -> AsyncIterator[dict[str, Any]]:
        yield event_tool_call(task.task_id, "bbx_list_tools", args={})
        result = await self._run_cli(["skill"], task.config)
        methods = result.get("methods")
        if not isinstance(methods, dict):
            raise RuntimeInvocationError("BBX skill response did not contain methods", "ValueError")
        yield event_tool_result(task.task_id, "bbx_list_tools", result=result)
        yield event_done(task.task_id, result=result)

    async def _invoke_health(self, task: AgentTask) -> AsyncIterator[dict[str, Any]]:
        yield event_tool_call(task.task_id, "bbx_health", args={})
        result = await self._run_cli(["status"], task.config)
        yield event_tool_result(
            task.task_id,
            "bbx_health",
            result=result,
            is_error=result.get("ok") is not True,
        )
        if result.get("ok") is not True:
            yield event_error(
                task.task_id,
                _result_error_message(result, "BBX is not ready"),
                error_type="BbxHealthError",
            )
            return
        yield event_done(task.task_id, result={"health": result})

    async def _invoke_call_tool(self, task: AgentTask) -> AsyncIterator[dict[str, Any]]:
        tool_name, tab_id, params = _tool_call_request(task)
        if not tool_name:
            yield event_error(
                task.task_id,
                'BBX tool call requires input.tool/name or workflow="<method_name>"',
                error_type="ValueError",
            )
            return

        arguments = {"params": params, **({"tabId": tab_id} if tab_id is not None else {})}
        yield event_tool_call(task.task_id, tool_name, args=arguments)
        args = ["call"]
        if tab_id is not None:
            args.extend(["--tab", str(tab_id)])
        args.extend([tool_name, json.dumps(params, separators=(",", ":"), ensure_ascii=False)])
        result = await self._run_cli(args, task.config)
        is_error = result.get("ok") is False
        yield event_tool_result(
            task.task_id,
            tool_name,
            result=result,
            is_error=is_error,
        )
        if is_error:
            yield event_error(
                task.task_id,
                _result_error_message(result, f"BBX method {tool_name!r} failed"),
                error_type="BbxToolError",
            )
            return
        yield event_done(task.task_id, result={"tool": tool_name, "result": result})

    async def _run_cli(
        self,
        args: list[str],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        binary = _resolve_binary(config)
        if binary is None:
            raise RuntimeInvocationError("BBX CLI was not found on PATH", "FileNotFoundError")
        command = [binary]
        remote = _read_optional_string(config.get("remote"))
        if remote:
            command.extend(["--remote", remote])
        command.extend(args)

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=_timeout_seconds(config),
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        output = stdout.decode("utf-8", errors="replace").strip()
        error_output = stderr.decode("utf-8", errors="replace").strip()
        if not output:
            raise RuntimeInvocationError(
                f"BBX returned no JSON output: {error_output[:500]}",
                "BbxCliError",
            )
        try:
            payload = json.loads(output)
        except ValueError as exc:
            raise RuntimeInvocationError(
                f"BBX returned invalid JSON: {output[:500]}",
                "ValueError",
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeInvocationError("BBX response was not an object", "ValueError")
        if process.returncode not in {0, None} and payload.get("ok") is not False:
            raise RuntimeInvocationError(
                error_output or f"BBX exited with status {process.returncode}",
                "BbxCliError",
            )
        return payload


def _resolve_binary(config: dict[str, Any]) -> str | None:
    configured = _read_optional_string(config.get("binary")) or os.environ.get("BBX_BINARY")
    if configured:
        return configured
    return shutil.which("bbx.cmd") or shutil.which("bbx")


def _timeout_seconds(config: dict[str, Any]) -> float:
    raw = config.get("timeout_seconds")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw > 0:
        return float(raw)
    return _DEFAULT_TIMEOUT_SECONDS


def _tool_call_request(
    task: AgentTask,
) -> tuple[str, int | None, dict[str, Any]]:
    payload = task.input if isinstance(task.input, dict) else {}
    workflow = _read_optional_string(task.workflow) or ""
    tool_name = (
        _read_optional_string(payload.get("tool"))
        or _read_optional_string(payload.get("name"))
        or ("" if workflow in _CALL_WORKFLOWS else workflow)
    )
    arguments = payload.get("arguments", payload.get("args"))
    arguments = arguments if isinstance(arguments, dict) else {}
    raw_tab_id = arguments.get("tabId", payload.get("tabId"))
    tab_id = (
        raw_tab_id
        if isinstance(raw_tab_id, int) and not isinstance(raw_tab_id, bool)
        else None
    )
    raw_params = arguments.get("params", payload.get("params"))
    if isinstance(raw_params, dict):
        params = dict(raw_params)
    else:
        params = {
            str(key): value
            for key, value in arguments.items()
            if key not in {"tabId", "params"}
        }
    return tool_name, tab_id, params


def _result_error_message(result: dict[str, Any], fallback: str) -> str:
    summary = _read_optional_string(result.get("summary"))
    if summary:
        return summary
    error = result.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or fallback)
    return str(error) if error else fallback


def _read_optional_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = ["BbxRuntimeAdapter"]
