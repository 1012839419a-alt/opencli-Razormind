import pytest

from tests.fixtures.workflow_conformance import workflow_conformance_project


async def _bootstrap_workflow(client):
    workspace_id = (await client.get("/api/v1/workspaces")).json()["data"][0]["id"]
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/projects/bootstrap",
        json={
            "project": {"name": "Collaboration project", "slug": "collaboration"},
            "workflow": {"name": "Collaborative workflow", "graph": workflow_conformance_project()},
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    return workspace_id, data["project"]["id"], data["primary_workflow"]["id"]


def _room(workspace_id: str, project_id: str, workflow_id: str) -> str:
    return f"workspace:{workspace_id}:project:{project_id}:workflow:{workflow_id}"


@pytest.mark.asyncio
async def test_collaboration_authorize_returns_only_the_owning_workflow_room(client):
    workspace_id, project_id, workflow_id = await _bootstrap_workflow(client)
    room = _room(workspace_id, project_id, workflow_id)

    authorized = await client.post(
        "/api/v1/internal/collaboration/authorize", json={"room": room}
    )
    assert authorized.status_code == 200, authorized.text
    assert authorized.json()["data"] == {"room": room}

    malformed = await client.post(
        "/api/v1/internal/collaboration/authorize",
        json={"room": f"workspace:{workspace_id}:workflow:{workflow_id}"},
    )
    assert malformed.status_code == 400

    other_project = await client.post(
        "/api/v1/internal/collaboration/authorize",
        json={"room": _room(workspace_id, "not-the-owner", workflow_id)},
    )
    assert other_project.status_code == 404


@pytest.mark.asyncio
async def test_collaboration_snapshot_replaces_graph_entries_and_preserves_draft_metadata(client):
    workspace_id, project_id, workflow_id = await _bootstrap_workflow(client)
    room = _room(workspace_id, project_id, workflow_id)
    draft_url = (
        f"/api/v1/workspaces/{workspace_id}/projects/{project_id}"
        f"/workflows/{workflow_id}/draft"
    )
    original = (await client.get(draft_url)).json()["data"]["graph"]
    nodes = [
        {
            **node,
            "ui": {
                **(node.get("ui") or {}),
                "position": {"x": 240 + index, "y": 120 + index},
            },
        }
        for index, node in enumerate(original["nodes"])
    ]
    edges = [
        {**edge, "label": f"collaborative-{index}"}
        for index, edge in enumerate(original["edges"])
    ]

    snapshot = await client.post(
        "/api/v1/internal/collaboration/snapshot",
        json={
            "room": room,
            "data": {
                "nodes": {"type": "Map", "content": {node["id"]: node for node in nodes}},
                "edges": {"type": "Map", "content": {edge["id"]: edge for edge in edges}},
            },
        },
    )
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["data"] == {"revision": 2}

    persisted = (await client.get(draft_url)).json()["data"]
    assert persisted["revision"] == 2
    assert persisted["updated_by_user_id"] == "collaboration-service"
    assert persisted["graph"]["name"] == original["name"]
    assert persisted["graph"]["settings"] == original["settings"]
    assert persisted["graph"]["adapters"] == original["adapters"]
    assert persisted["graph"]["nodes"] == nodes
    assert persisted["graph"]["edges"] == edges
