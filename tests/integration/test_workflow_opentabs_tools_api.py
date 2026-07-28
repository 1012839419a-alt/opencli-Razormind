from __future__ import annotations

import httpx
import pytest

from backend.agent_runtimes.opentabs_adapter import OpenTabsRuntimeAdapter


def _mock_opentabs_client(monkeypatch, handler) -> None:
    monkeypatch.setattr(
        OpenTabsRuntimeAdapter,
        "_client",
        lambda self, config: httpx.AsyncClient(
            base_url="http://opentabs.local",
            transport=httpx.MockTransport(handler),
        ),
    )


@pytest.mark.asyncio
async def test_opentabs_tools_are_projected_as_callable_workflow_nodes(
    client,
    monkeypatch,
):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/tools"
        return httpx.Response(
            200,
            json=[
                {
                    "name": "browser_list_tabs",
                    "description": "List open browser tabs",
                    "plugin": "browser",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                    },
                    "annotations": {"readOnlyHint": True},
                },
                {
                    "name": "slack__send_message",
                    "description": "Send a Slack message",
                    "plugin": "slack",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string", "description": "Channel ID"},
                            "text": {"type": "string", "description": "Message text"},
                        },
                        "required": ["channel", "text"],
                    },
                    "annotations": {"readOnlyHint": False},
                },
            ],
        )

    _mock_opentabs_client(monkeypatch, handler)

    response = await client.get("/api/v1/workflows/opentabs-tool-nodes")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["available"] is True
    assert data["total"] == 2
    assert data["summary"]["plugins"] == {"browser": 1, "slack": 1}

    nodes = {node["tool"]: node for node in data["nodes"]}
    browser = nodes["browser_list_tabs"]
    assert browser["id"] == "opentabs.tool.browser.browser-list-tabs"
    assert browser["access"] == "read"
    assert browser["status"] == "runnable"
    assert browser["requiredArgs"] == []
    assert browser["params"]["toolCapability"] == {
        "id": "tool.opentabs.call",
        "executor": {
            "mode": "opentabs",
            "params": {
                "plugin": "browser",
                "readOnly": True,
                "tool": "browser_list_tabs",
            },
        },
    }

    slack = nodes["slack__send_message"]
    assert slack["access"] == "write"
    assert slack["status"] == "blocked"
    assert slack["requiredArgs"] == ["channel", "text"]
    assert [field["name"] for field in slack["args"]] == ["channel", "text"]
    assert slack["manifest"]["permissions"] == [
        "canvas_review_required",
        "canMutateExternalSites",
        "opentabs_tool_permission",
    ]


@pytest.mark.asyncio
async def test_opentabs_tool_node_compiles_and_runs_through_runtime_adapter(
    client,
    monkeypatch,
):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/tools/browser_list_tabs/call"
        assert request.read() == b'{"arguments":{"windowId":7}}'
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": '[{"id":1,"title":"OpenTabs"}]',
                    }
                ]
            },
        )

    _mock_opentabs_client(monkeypatch, handler)
    project = {
        "id": "wf-opentabs-browser",
        "name": "OpenTabs browser test",
        "profile": "intelligence",
        "version": 1,
        "nodes": [
            {
                "id": "list-tabs",
                "kind": "action",
                "capability": "store",
                "params": {
                    "toolCapability": {
                        "id": "tool.opentabs.call",
                        "executor": {
                            "mode": "opentabs",
                            "params": {
                                "tool": "browser_list_tabs",
                                "plugin": "browser",
                                "readOnly": True,
                            },
                        },
                    },
                    "toolParams": {"windowId": 7},
                    "opentabsTool": {
                        "name": "browser_list_tabs",
                        "plugin": "browser",
                        "access": "read",
                    },
                },
                "ui": {
                    "catalogId": "external.tool.capability",
                    "adapterNodeId": "opentabs.tool.browser.browser-list-tabs",
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
    assert binding["input"]["executorMode"] == "opentabs"
    assert binding["input"]["executorParams"]["tool"] == "browser_list_tabs"

    run = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-opentabs-browser",
            "traceId": "trace-opentabs-browser",
        },
    )

    assert run.status_code == 202
    assert run.json()["data"]["status"] == "completed"
    events = (
        await client.get("/api/v1/workflows/runs/run-opentabs-browser/events")
    ).json()["data"]
    partial = next(
        event
        for event in events
        if event["nodeId"] == "list-tabs" and event["eventType"] == "partial"
    )
    assert partial["details"]["executorMode"] == "opentabs"
    assert partial["details"]["outputItemCount"] == 1
    assert partial["details"]["sampleOutputs"][0]["id"] == 1
    assert partial["details"]["sampleOutputs"][0]["title"] == "OpenTabs"
