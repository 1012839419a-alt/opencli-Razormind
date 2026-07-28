from __future__ import annotations

import pytest

from backend.agent_runtimes.base import AgentTask
from backend.agent_runtimes.bbx_adapter import BbxRuntimeAdapter


async def _collect(adapter: BbxRuntimeAdapter, task: AgentTask) -> list[dict]:
    return [event async for event in adapter.invoke(task)]


@pytest.mark.asyncio
async def test_list_tools_projects_bbx_runtime_methods(monkeypatch):
    calls: list[list[str]] = []

    async def fake_run(self, args, config):
        calls.append(args)
        return {
            "v": "1.7",
            "methods": {
                "page": ["page.get_state", "page.get_text"],
                "inspect": ["dom.query"],
                "interact": ["input.click"],
            },
        }

    monkeypatch.setattr(BbxRuntimeAdapter, "_run_cli", fake_run)
    events = await _collect(
        BbxRuntimeAdapter(),
        AgentTask(task_id="bbx-list", workflow="tool.list"),
    )

    assert calls == [["skill"]]
    assert events[-1]["type"] == "done"
    assert events[-1]["result"]["methods"]["page"] == [
        "page.get_state",
        "page.get_text",
    ]


@pytest.mark.asyncio
async def test_call_tool_passes_tab_and_json_params_to_bbx(monkeypatch):
    calls: list[list[str]] = []

    async def fake_run(self, args, config):
        calls.append(args)
        return {
            "ok": True,
            "summary": "Page text read.",
            "evidence": {"text": "OpenCLI"},
        }

    monkeypatch.setattr(BbxRuntimeAdapter, "_run_cli", fake_run)
    events = await _collect(
        BbxRuntimeAdapter(),
        AgentTask(
            task_id="bbx-call",
            workflow="tool.call",
            input={
                "tool": "page.get_text",
                "arguments": {"tabId": 27, "params": {"textBudget": 600}},
            },
        ),
    )

    assert calls == [
        [
            "call",
            "--tab",
            "27",
            "page.get_text",
            '{"textBudget":600}',
        ]
    ]
    assert events[-1]["type"] == "done"
    assert events[-1]["result"]["result"]["evidence"]["text"] == "OpenCLI"
