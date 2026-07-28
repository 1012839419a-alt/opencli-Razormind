"""Project live OpenTabs tools into callable Canvas tool nodes."""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from typing import Any

from backend.agent_runtimes.base import AgentTask
from backend.agent_runtimes.opentabs_adapter import OpenTabsRuntimeAdapter
from backend.schemas.workflow import (
    WorkflowOpenCLIAdapterNodeArg,
    WorkflowOpenTabsToolNode,
    WorkflowOpenTabsToolNodesResponse,
)

OPENTABS_TOOL_CAPABILITY_ID = "tool.opentabs.call"
OPENTABS_EXECUTOR_MODE = "opentabs"
_EXTERNAL_TOOL_BINDING_ID = "workflow.external-tool.capability"


class OpenTabsToolExecutionError(RuntimeError):
    """Raised when OpenTabs returns a terminal runtime error."""


async def list_opentabs_tool_nodes(
    *,
    plugin: str | None = None,
    q: str | None = None,
    include_write: bool = True,
    limit: int = 2000,
) -> WorkflowOpenTabsToolNodesResponse:
    adapter = OpenTabsRuntimeAdapter()
    task = AgentTask(
        task_id=f"opentabs-discovery-{uuid.uuid4()}",
        workflow="tool.list",
        input={"plugin": plugin} if plugin else {},
        config={"timeout_seconds": 5},
    )
    events = [event async for event in adapter.invoke(task)]
    error = next((event for event in events if event.get("type") == "error"), None)
    if error is not None:
        return WorkflowOpenTabsToolNodesResponse(
            available=False,
            total=0,
            summary={"plugins": {}, "access": {"read": 0, "write": 0}},
            reason=_read_string(error.get("message")) or "OpenTabs runtime unavailable",
            nodes=[],
        )

    done = next((event for event in reversed(events) if event.get("type") == "done"), None)
    result = _read_dict(done.get("result")) if done else {}
    raw_tools = result.get("tools")
    tools = (
        [tool for tool in raw_tools if isinstance(tool, dict)]
        if isinstance(raw_tools, list)
        else []
    )
    nodes = project_opentabs_tools(tools)
    if not include_write:
        nodes = [node for node in nodes if node.access == "read"]
    if plugin:
        plugin_key = plugin.strip().lower()
        nodes = [node for node in nodes if node.plugin.lower() == plugin_key]
    if q:
        needle = q.strip().lower()
        nodes = [
            node
            for node in nodes
            if needle in node.tool.lower()
            or needle in node.plugin.lower()
            or needle in node.label.lower()
            or needle in node.description.lower()
        ]
    nodes.sort(key=lambda node: (node.plugin, node.tool))
    total = len(nodes)
    summary = _summarize(nodes)
    return WorkflowOpenTabsToolNodesResponse(
        available=True,
        total=total,
        summary=summary,
        nodes=nodes[:limit],
    )


def project_opentabs_tools(tools: list[dict[str, Any]]) -> list[WorkflowOpenTabsToolNode]:
    """Build stable, conservative node manifests from OpenTabs ``GET /tools``."""

    nodes: list[WorkflowOpenTabsToolNode] = []
    seen: set[str] = set()
    for tool in tools:
        tool_name = _read_string(tool.get("name"))
        if not tool_name or tool_name in seen:
            continue
        seen.add(tool_name)
        plugin = _tool_plugin(tool_name, tool)
        input_schema = _read_dict(tool.get("inputSchema"))
        args = _schema_args(input_schema)
        required_args = [arg.name for arg in args if arg.required]
        access = _tool_access(tool)
        read_only = access == "read"
        status = "runnable" if read_only and not required_args else "blocked"
        display_name = (
            _read_string(tool.get("displayName"))
            or _read_string(tool.get("title"))
            or tool_name
        )
        node_id = f"opentabs.tool.{_safe_id(plugin)}.{_safe_id(tool_name)}"
        permissions = (
            ["canFetchNetwork", "opentabs_tool_permission"]
            if read_only
            else [
                "canvas_review_required",
                "canMutateExternalSites",
                "opentabs_tool_permission",
            ]
        )
        nodes.append(
            WorkflowOpenTabsToolNode(
                id=node_id,
                label=f"{plugin} · {display_name}",
                description=_read_string(tool.get("description")) or "",
                status=status,
                plugin=plugin,
                tool=tool_name,
                access=access,
                requiredArgs=required_args,
                args=args,
                inputSchema=input_schema,
                params={
                    "toolCapability": {
                        "id": OPENTABS_TOOL_CAPABILITY_ID,
                        "executor": {
                            "mode": OPENTABS_EXECUTOR_MODE,
                            "params": {
                                "tool": tool_name,
                                "plugin": plugin,
                                "readOnly": read_only,
                            },
                        },
                    },
                    "toolParams": {},
                    "opentabsTool": {
                        "name": tool_name,
                        "plugin": plugin,
                        "access": access,
                    },
                },
                manifest={
                    "schema": "opentabs.tool-node.v1",
                    "runtime": {
                        "binding": _EXTERNAL_TOOL_BINDING_ID,
                        "executor": OPENTABS_EXECUTOR_MODE,
                    },
                    "permissions": permissions,
                    "opentabs": {
                        "tool": tool_name,
                        "plugin": plugin,
                        "access": access,
                        "annotations": _read_dict(tool.get("annotations")),
                    },
                    "canvas": {
                        "node": True,
                        "catalogId": "external.tool.capability",
                        "requiredArgs": required_args,
                        "reviewRequired": not read_only,
                    },
                    "trace": {
                        "events": [
                            "tool_call_started",
                            "partial:outputItemCount",
                            "tool_call_completed",
                            "completed",
                        ]
                    },
                },
            )
        )
    return nodes


async def invoke_opentabs_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    task_id: str,
) -> dict[str, Any]:
    """Invoke one OpenTabs tool and return its MCP-style tool result."""

    adapter = OpenTabsRuntimeAdapter()
    task = AgentTask(
        task_id=task_id,
        workflow="tool.call",
        input={"tool": tool_name, "arguments": arguments},
        config={},
    )
    events = [event async for event in adapter.invoke(task)]
    error = next((event for event in events if event.get("type") == "error"), None)
    if error is not None:
        raise OpenTabsToolExecutionError(
            _read_string(error.get("message")) or f"OpenTabs tool {tool_name!r} failed"
        )
    done = next((event for event in reversed(events) if event.get("type") == "done"), None)
    if done is None:
        raise OpenTabsToolExecutionError(
            f"OpenTabs tool {tool_name!r} returned no terminal result"
        )
    result = _read_dict(_read_dict(done.get("result")).get("result"))
    if not result:
        raise OpenTabsToolExecutionError(
            f"OpenTabs tool {tool_name!r} returned an empty result"
        )
    return result


def opentabs_result_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize MCP content/structuredContent into workflow item objects."""

    structured = result.get("structuredContent")
    if isinstance(structured, list):
        items = [_as_item(item) for item in structured]
        return [item for item in items if item is not None]
    if isinstance(structured, dict):
        return [dict(structured)]

    items: list[dict[str, Any]] = []
    content = result.get("content")
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                items.extend(_text_items(part["text"]))
            else:
                items.append(dict(part))
    return items or [{"result": result}]


def _text_items(text: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(text)
    except ValueError:
        return [{"text": text}]
    if isinstance(value, list):
        return [item for entry in value if (item := _as_item(entry)) is not None]
    item = _as_item(value)
    return [item] if item is not None else []


def _as_item(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return None
    return {"value": value}


def _schema_args(input_schema: dict[str, Any]) -> list[WorkflowOpenCLIAdapterNodeArg]:
    properties = _read_dict(input_schema.get("properties"))
    required = {
        name for name in input_schema.get("required", []) if isinstance(name, str)
    }
    args: list[WorkflowOpenCLIAdapterNodeArg] = []
    for name, raw_schema in properties.items():
        if not isinstance(name, str) or not isinstance(raw_schema, dict):
            continue
        args.append(
            WorkflowOpenCLIAdapterNodeArg(
                name=name,
                type=_read_string(raw_schema.get("type")),
                required=name in required,
                valueRequired=name in required,
                choices=(
                    list(raw_schema["enum"])
                    if isinstance(raw_schema.get("enum"), list)
                    else []
                ),
                default=raw_schema.get("default"),
                help=_read_string(raw_schema.get("description")),
            )
        )
    return args


def _tool_access(tool: dict[str, Any]) -> str:
    annotations = _read_dict(tool.get("annotations"))
    return "read" if annotations.get("readOnlyHint") is True else "write"


def _tool_plugin(tool_name: str, tool: dict[str, Any]) -> str:
    explicit = _read_string(tool.get("plugin"))
    if explicit:
        return explicit
    if "__" in tool_name:
        return tool_name.split("__", 1)[0]
    if tool_name.startswith("browser_"):
        return "browser"
    return "opentabs"


def _summarize(nodes: list[WorkflowOpenTabsToolNode]) -> dict[str, Any]:
    return {
        "plugins": dict(sorted(Counter(node.plugin for node in nodes).items())),
        "access": dict(sorted(Counter(node.access for node in nodes).items())),
    }


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "tool"


def _read_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = [
    "OPENTABS_EXECUTOR_MODE",
    "OPENTABS_TOOL_CAPABILITY_ID",
    "OpenTabsToolExecutionError",
    "invoke_opentabs_tool",
    "list_opentabs_tool_nodes",
    "opentabs_result_items",
    "project_opentabs_tools",
]
