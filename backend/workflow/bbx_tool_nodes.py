"""Project Browser Bridge (BBX) methods into callable Canvas tool nodes."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Any

from backend.agent_runtimes.base import AgentTask
from backend.agent_runtimes.bbx_adapter import BbxRuntimeAdapter
from backend.schemas.workflow import (
    WorkflowBbxToolNode,
    WorkflowBbxToolNodesResponse,
    WorkflowOpenCLIAdapterNodeArg,
)

BBX_TOOL_CAPABILITY_ID = "tool.bbx.call"
BBX_EXECUTOR_MODE = "bbx"
_EXTERNAL_TOOL_BINDING_ID = "workflow.external-tool.capability"

_WRITE_METHOD_PREFIXES = (
    "access.",
    "input.",
    "navigation.",
    "patch.apply",
    "patch.rollback",
    "patch.commit",
    "setup.install",
    "tabs.activate",
    "tabs.close",
    "tabs.create",
    "viewport.",
)
_WRITE_METHODS = {
    "cdp.dispatch_key_event",
    "network.intercept.add",
    "network.intercept.clear",
    "network.intercept.remove",
    "page.evaluate",
}

_METHOD_DESCRIPTIONS = {
    "tabs.list": "列出当前已授权浏览器窗口中的标签页",
    "page.get_state": "读取当前页面 URL、标题、来源和加载状态",
    "page.get_console": "读取页面控制台输出",
    "page.get_storage": "读取页面 localStorage 或 sessionStorage",
    "page.get_text": "读取当前页面中有界的可见文本",
    "page.get_network": "读取页面最近的 Fetch/XHR 网络活动",
    "dom.query": "查询 DOM 子树并返回紧凑的节点摘要",
    "dom.describe": "读取一个 BBX elementRef 的详细信息",
    "dom.get_text": "读取一个元素的有界文本",
    "dom.get_attributes": "读取一个元素的指定属性",
    "dom.find_by_text": "按可见文本查找页面元素",
    "dom.find_by_role": "按 ARIA 角色和名称查找页面元素",
    "dom.get_html": "读取一个元素的内部或外部 HTML",
    "styles.get_computed": "读取一个元素的计算样式",
    "layout.get_box_model": "读取一个元素的盒模型",
    "performance.get_metrics": "读取浏览器页面性能指标",
    "input.click": "点击页面元素",
    "input.type": "向页面元素输入文本",
    "input.fill": "设置输入框或文本域的值",
    "navigation.navigate": "导航当前标签页到指定 URL",
}


class BbxToolExecutionError(RuntimeError):
    """Raised when BBX returns a terminal runtime error."""


async def list_bbx_tool_nodes(
    *,
    group: str | None = None,
    q: str | None = None,
    include_write: bool = True,
    limit: int = 2000,
) -> WorkflowBbxToolNodesResponse:
    adapter = BbxRuntimeAdapter()
    task = AgentTask(
        task_id=f"bbx-discovery-{uuid.uuid4()}",
        workflow="tool.list",
        config={"timeout_seconds": 5},
    )
    events = [event async for event in adapter.invoke(task)]
    error = next((event for event in events if event.get("type") == "error"), None)
    if error is not None:
        return WorkflowBbxToolNodesResponse(
            available=False,
            total=0,
            summary={"groups": {}, "access": {"read": 0, "write": 0}},
            reason=_read_string(error.get("message")) or "BBX runtime unavailable",
            nodes=[],
        )

    done = next((event for event in reversed(events) if event.get("type") == "done"), None)
    result = _read_dict(done.get("result")) if done else {}
    nodes = project_bbx_methods(_read_dict(result.get("methods")))
    if not include_write:
        nodes = [node for node in nodes if node.access == "read"]
    if group:
        group_key = group.strip().lower()
        nodes = [node for node in nodes if node.group.lower() == group_key]
    if q:
        needle = q.strip().lower()
        nodes = [
            node
            for node in nodes
            if needle in node.tool.lower()
            or needle in node.group.lower()
            or needle in node.label.lower()
            or needle in node.description.lower()
        ]
    nodes.sort(key=lambda node: (node.group, node.tool))
    total = len(nodes)
    return WorkflowBbxToolNodesResponse(
        available=True,
        total=total,
        summary=_summarize(nodes),
        nodes=nodes[:limit],
    )


def project_bbx_methods(method_groups: dict[str, Any]) -> list[WorkflowBbxToolNode]:
    nodes: list[WorkflowBbxToolNode] = []
    seen: set[str] = set()
    for group, raw_methods in method_groups.items():
        if not isinstance(group, str) or not isinstance(raw_methods, list):
            continue
        for raw_method in raw_methods:
            method = _read_string(raw_method)
            if not method or method in seen:
                continue
            seen.add(method)
            access = _method_access(method)
            read_only = access == "read"
            permissions = (
                ["canFetchNetwork", "bbx_access_enabled"]
                if read_only
                else [
                    "canvas_review_required",
                    "canMutateExternalSites",
                    "bbx_access_enabled",
                ]
            )
            nodes.append(
                WorkflowBbxToolNode(
                    id=f"bbx.tool.{_safe_id(group)}.{_safe_id(method)}",
                    label=f"BBX · {method}",
                    description=_METHOD_DESCRIPTIONS.get(
                        method,
                        f"通过 Browser Bridge 调用 {method}",
                    ),
                    status="blocked",
                    group=group,
                    tool=method,
                    access=access,
                    requiredArgs=[],
                    args=[
                        WorkflowOpenCLIAdapterNodeArg(
                            name="tabId",
                            type="integer",
                            required=False,
                            valueRequired=False,
                            help="可选；指定 BBX 标签页 ID，留空时使用当前路由标签页",
                        ),
                        WorkflowOpenCLIAdapterNodeArg(
                            name="params",
                            type="object",
                            required=False,
                            valueRequired=False,
                            help='可选；此 BBX 方法的 JSON 参数，例如 {"textBudget":600}',
                        ),
                    ],
                    params={
                        "toolCapability": {
                            "id": BBX_TOOL_CAPABILITY_ID,
                            "executor": {
                                "mode": BBX_EXECUTOR_MODE,
                                "params": {
                                    "tool": method,
                                    "group": group,
                                    "readOnly": read_only,
                                },
                            },
                        },
                        "toolParams": {},
                        "bbxTool": {
                            "name": method,
                            "group": group,
                            "access": access,
                        },
                    },
                    manifest={
                        "schema": "bbx.tool-node.v1",
                        "runtime": {
                            "binding": _EXTERNAL_TOOL_BINDING_ID,
                            "executor": BBX_EXECUTOR_MODE,
                        },
                        "permissions": permissions,
                        "bbx": {
                            "tool": method,
                            "group": group,
                            "access": access,
                        },
                        "canvas": {
                            "node": True,
                            "catalogId": "external.tool.capability",
                            "requiredArgs": [],
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


async def invoke_bbx_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    task_id: str,
) -> dict[str, Any]:
    adapter = BbxRuntimeAdapter()
    task = AgentTask(
        task_id=task_id,
        workflow="tool.call",
        input={"tool": tool_name, "arguments": arguments},
        config={},
    )
    events = [event async for event in adapter.invoke(task)]
    error = next((event for event in events if event.get("type") == "error"), None)
    if error is not None:
        raise BbxToolExecutionError(
            _read_string(error.get("message")) or f"BBX method {tool_name!r} failed"
        )
    done = next((event for event in reversed(events) if event.get("type") == "done"), None)
    if done is None:
        raise BbxToolExecutionError(f"BBX method {tool_name!r} returned no terminal result")
    result = _read_dict(_read_dict(done.get("result")).get("result"))
    if not result:
        raise BbxToolExecutionError(f"BBX method {tool_name!r} returned an empty result")
    return result


def bbx_result_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = result.get("evidence")
    if isinstance(evidence, list):
        return [_as_item(item) for item in evidence]
    if isinstance(evidence, dict):
        for key in ("items", "nodes", "tabs", "entries", "results"):
            values = evidence.get(key)
            if isinstance(values, list):
                return [_as_item(item) for item in values]
        return [dict(evidence)]
    return [dict(result)]


def _as_item(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {"value": value}


def _method_access(method: str) -> str:
    if method in _WRITE_METHODS or method.startswith(_WRITE_METHOD_PREFIXES):
        return "write"
    return "read"


def _summarize(nodes: list[WorkflowBbxToolNode]) -> dict[str, Any]:
    return {
        "groups": dict(sorted(Counter(node.group for node in nodes).items())),
        "access": dict(sorted(Counter(node.access for node in nodes).items())),
    }


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "tool"


def _read_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = [
    "BBX_EXECUTOR_MODE",
    "BBX_TOOL_CAPABILITY_ID",
    "BbxToolExecutionError",
    "bbx_result_items",
    "invoke_bbx_tool",
    "list_bbx_tool_nodes",
    "project_bbx_methods",
]
