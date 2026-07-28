from __future__ import annotations

import pytest

from backend.agent_runtimes.bbx_adapter import BbxRuntimeAdapter


def _mock_bbx_cli(monkeypatch, handler) -> None:
    monkeypatch.setattr(BbxRuntimeAdapter, "_run_cli", handler)


@pytest.mark.asyncio
async def test_bbx_methods_are_projected_as_callable_workflow_nodes(
    client,
    monkeypatch,
):
    async def handler(self, args, config):
        assert args == ["skill"]
        return {
            "v": "1.7",
            "methods": {
                "page": ["page.get_text"],
                "inspect": ["dom.query"],
                "interact": ["input.click"],
            },
        }

    _mock_bbx_cli(monkeypatch, handler)

    response = await client.get("/api/v1/workflows/bbx-tool-nodes")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["available"] is True
    assert data["total"] == 3

    nodes = {node["tool"]: node for node in data["nodes"]}
    page_text = nodes["page.get_text"]
    assert page_text["access"] == "read"
    assert page_text["params"]["toolCapability"]["executor"] == {
        "mode": "bbx",
        "params": {
            "group": "page",
            "readOnly": True,
            "tool": "page.get_text",
        },
    }
    assert nodes["input.click"]["access"] == "write"


@pytest.mark.asyncio
async def test_bbx_tool_node_compiles_and_runs_through_runtime_adapter(
    client,
    monkeypatch,
):
    async def handler(self, args, config):
        assert args == [
            "call",
            "--tab",
            "27",
            "page.get_text",
            '{"textBudget":600}',
        ]
        return {
            "ok": True,
            "summary": "Page text read.",
            "evidence": {"text": "OpenCLI Admin"},
        }

    _mock_bbx_cli(monkeypatch, handler)
    project = {
        "id": "wf-bbx-page-text",
        "name": "BBX page text test",
        "profile": "intelligence",
        "version": 1,
        "nodes": [
            {
                "id": "read-page-text",
                "kind": "action",
                "capability": "store",
                "params": {
                    "toolCapability": {
                        "id": "tool.bbx.call",
                        "executor": {
                            "mode": "bbx",
                            "params": {
                                "tool": "page.get_text",
                                "group": "page",
                                "readOnly": True,
                            },
                        },
                    },
                    "toolParams": {
                        "tabId": 27,
                        "params": {"textBudget": 600},
                    },
                    "bbxTool": {
                        "name": "page.get_text",
                        "group": "page",
                        "access": "read",
                    },
                },
                "ui": {
                    "catalogId": "external.tool.capability",
                    "adapterNodeId": "bbx.tool.page.page-get-text",
                },
            }
        ],
        "edges": [],
        "adapters": [],
        "agentPermissions": {
            "canFetchNetwork": True,
            "canSendNotifications": False,
            "canWriteInbox": True,
            "canMutateExternalSites": False,
        },
    }

    compiled = await client.post("/api/v1/workflows/compile", json={"project": project})

    assert compiled.status_code == 200
    compiled_data = compiled.json()["data"]
    assert compiled_data["valid"] is True, compiled_data["errors"]
    binding = compiled_data["plan"]["runtime"]["nodes"][0]["runtime"]["binding"]
    assert binding["binding_id"] == "workflow.external-tool.capability"
    assert binding["input"]["executorMode"] == "bbx"

    run = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-bbx-page-text",
            "traceId": "trace-bbx-page-text",
        },
    )

    assert run.status_code == 202
    assert run.json()["data"]["status"] == "completed"
    events = (
        await client.get("/api/v1/workflows/runs/run-bbx-page-text/events")
    ).json()["data"]
    partial = next(
        event
        for event in events
        if event["nodeId"] == "read-page-text" and event["eventType"] == "partial"
    )
    assert partial["details"]["executorMode"] == "bbx"
    assert partial["details"]["sampleOutputs"][0]["text"] == "OpenCLI Admin"
