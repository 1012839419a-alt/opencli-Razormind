import pytest
from sqlalchemy import select

from backend.models.studio import StudioProject, StudioWorkflow, StudioWorkspace
from backend.services import image_studio_service
from tests.fixtures.workflow_conformance import workflow_conformance_project


async def _create_studio_workflow(client, *, graph: dict | None = None) -> dict:
    workspace_id = (await client.get("/api/v1/workspaces")).json()["data"][0]["id"]
    result = (
        await client.post(
            f"/api/v1/workspaces/{workspace_id}/projects/bootstrap",
            json={
                "project": {
                    "name": "Lifecycle project",
                    "slug": "lifecycle-project",
                },
                "workflow": {
                    "name": "Lifecycle workflow",
                    "graph": graph or workflow_conformance_project(),
                },
            },
        )
    ).json()["data"]
    project = result["project"]
    workflow = result["primary_workflow"]
    base_url = (
        f"/api/v1/workspaces/{workspace_id}/projects/{project['id']}"
        f"/workflows/{workflow['id']}"
    )
    return {"workflow": workflow, "base_url": base_url}


@pytest.mark.asyncio
async def test_studio_legacy_graph_extensions_and_nested_nulls_round_trip(client):
    graph = workflow_conformance_project()
    graph["legacyExtension"] = {
        "schema": "legacy-extension.v0",
        "nullableValue": None,
    }
    graph["nodes"][0]["legacyNodeExtension"] = {
        "owner": "legacy-canvas",
        "nullableValue": None,
    }
    graph["nodes"][0]["sourceAnchor"] = None

    created = await _create_studio_workflow(client, graph=graph)
    draft_url = f"{created['base_url']}/draft"
    first = await client.get(draft_url)

    assert first.status_code == 200, first.text
    first_draft = first.json()["data"]
    first_graph = first_draft["graph"]
    assert first_graph["legacyExtension"] == graph["legacyExtension"]
    assert first_graph["nodes"][0]["legacyNodeExtension"] == (
        graph["nodes"][0]["legacyNodeExtension"]
    )
    assert "sourceAnchor" not in first_graph["nodes"][0]

    first_graph["legacyExtension"]["revisionNote"] = "round-trip"
    first_graph["nodes"][0]["legacyNodeExtension"]["revision"] = 2
    updated = await client.put(
        draft_url,
        json={"graph": first_graph, "revision": first_draft["revision"]},
    )

    assert updated.status_code == 200, updated.text
    updated_graph = updated.json()["data"]["graph"]
    assert updated_graph["legacyExtension"] == first_graph["legacyExtension"]
    assert updated_graph["nodes"][0]["legacyNodeExtension"] == (
        first_graph["nodes"][0]["legacyNodeExtension"]
    )

    reloaded = await client.get(draft_url)
    assert reloaded.status_code == 200, reloaded.text
    assert reloaded.json()["data"]["graph"] == updated_graph


@pytest.mark.asyncio
async def test_studio_workflow_draft_validation_run_is_persisted(client):
    created = await _create_studio_workflow(client)
    response = await client.post(
        f"{created['base_url']}/draft/validation-runs",
        json={},
    )

    assert response.status_code == 201, response.text
    run = response.json()["data"]
    assert run["workflowId"] == created["workflow"]["id"]
    assert run["status"] == "completed"
    assert run["valid"] is True
    assert run["draftRevision"] == 1
    assert run["errors"] == []
    assert run["warnings"] == []
    assert run["runId"]


@pytest.mark.asyncio
async def test_studio_workflow_current_validated_revision_can_be_published(client):
    created = await _create_studio_workflow(client)
    validation = (
        await client.post(f"{created['base_url']}/draft/validation-runs", json={})
    ).json()["data"]
    response = await client.post(
        f"{created['base_url']}/versions",
        json={
            "reason": "Release validated workflow",
            "expectedRevision": 1,
            "validationRunId": validation["runId"],
        },
    )

    assert response.status_code == 201, response.text
    version = response.json()["data"]
    assert version["workflow_id"] == created["workflow"]["id"]
    assert version["version"] == 1
    assert version["draft_revision"] == 1
    assert version["graph"]["id"] == created["workflow"]["id"]
    assert version["compile_version"] == "1.1.0"
    assert version["published_by_user_id"] == "local-development-user"
    assert version["reason"] == "Release validated workflow"

    listed = await client.get(f"{created['base_url']}/versions")
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"] == [version]
    workflows_url = created["base_url"].rsplit("/", 1)[0]
    workflow = (await client.get(workflows_url)).json()["data"][0]
    assert workflow["current_published_version"] == 1


@pytest.mark.asyncio
async def test_studio_workflow_rejects_validation_from_an_older_draft_revision(client):
    created = await _create_studio_workflow(client)
    validation = (
        await client.post(f"{created['base_url']}/draft/validation-runs", json={})
    ).json()["data"]
    draft_url = f"{created['base_url']}/draft"
    draft = (await client.get(draft_url)).json()["data"]
    updated = await client.put(
        draft_url,
        json={
            "graph": {**draft["graph"], "name": "Updated after validation"},
            "revision": draft["revision"],
        },
    )
    assert updated.status_code == 200, updated.text

    response = await client.post(
        f"{created['base_url']}/versions",
        json={
            "reason": "Attempt stale release",
            "expectedRevision": 2,
            "validationRunId": validation["runId"],
        },
    )
    assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_studio_workflow_rejects_failed_validation_for_current_revision(client):
    invalid_graph = workflow_conformance_project()
    invalid_graph["nodes"].append(dict(invalid_graph["nodes"][0]))
    created = await _create_studio_workflow(client, graph=invalid_graph)
    validation_response = await client.post(
        f"{created['base_url']}/draft/validation-runs",
        json={},
    )
    assert validation_response.status_code == 201, validation_response.text
    validation = validation_response.json()["data"]
    assert validation["status"] == "failed"
    assert validation["valid"] is False
    assert validation["errors"]

    response = await client.post(
        f"{created['base_url']}/versions",
        json={
            "reason": "Invalid release",
            "expectedRevision": 1,
            "validationRunId": validation["runId"],
        },
    )
    assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_studio_workflow_versions_keep_immutable_graph_snapshots(client):
    original_graph = workflow_conformance_project()
    created = await _create_studio_workflow(client, graph=original_graph)
    first_validation = (
        await client.post(f"{created['base_url']}/draft/validation-runs", json={})
    ).json()["data"]
    first = await client.post(
        f"{created['base_url']}/versions",
        json={
            "reason": "First release",
            "expectedRevision": 1,
            "validationRunId": first_validation["runId"],
        },
    )
    assert first.status_code == 201, first.text

    draft_url = f"{created['base_url']}/draft"
    draft = (await client.get(draft_url)).json()["data"]
    updated = await client.put(
        draft_url,
        json={
            "graph": {**draft["graph"], "name": "Second revision"},
            "revision": draft["revision"],
        },
    )
    assert updated.status_code == 200, updated.text
    second_validation = (
        await client.post(f"{created['base_url']}/draft/validation-runs", json={})
    ).json()["data"]
    second = await client.post(
        f"{created['base_url']}/versions",
        json={
            "reason": "Second release",
            "expectedRevision": 2,
            "validationRunId": second_validation["runId"],
        },
    )
    assert second.status_code == 201, second.text

    versions = (await client.get(f"{created['base_url']}/versions")).json()["data"]
    assert [(item["version"], item["graph"]["name"]) for item in versions] == [
        (2, "Second revision"),
        (1, original_graph["name"]),
    ]


@pytest.mark.asyncio
async def test_image_canvas_document_is_fixed_to_snapshot_during_validation_and_publish(
    client, db_session
):
    created = await _create_studio_workflow(client)
    workflow_id = created["workflow"]["id"]
    workflow = await db_session.scalar(
        select(StudioWorkflow).where(StudioWorkflow.id == workflow_id)
    )
    assert workflow is not None
    project = await db_session.scalar(
        select(StudioProject).where(StudioProject.id == workflow.project_id)
    )
    assert project is not None
    workspace = await db_session.scalar(
        select(StudioWorkspace).where(StudioWorkspace.id == project.workspace_id)
    )
    assert workspace is not None

    document = await image_studio_service.create_document(
        db_session,
        workspace_id=workspace.id,
        project_id=project.id,
        workflow_id=workflow.id,
        node_id="generate-hero",
        document={"version": 1, "layers": [], "settings": {}},
        updated_by_user_id="test-user",
    )
    snapshot = await image_studio_service.create_snapshot(
        db_session,
        document=document,
        expected_revision=1,
        executable_graph={"nodes": {"image": {"type": "test"}}},
        model_fingerprint="sha256:test-model",
        seed=42,
        lora_revisions=[],
        asset_ids=[],
        created_by_user_id="test-user",
    )
    graph = {
        "id": workflow.id,
        "name": "Published image workflow",
        "profile": "intelligence",
        "version": 1,
        "nodes": [
            {
                "id": "generate-hero",
                "kind": "media",
                "capability": "generate",
                "params": {"canvasDocumentId": document.id},
                "ui": {"catalogId": "media.image-generation"},
            }
        ],
        "edges": [],
    }
    updated = await client.put(
        f"{created['base_url']}/draft",
        json={"graph": graph, "revision": 1},
    )
    assert updated.status_code == 200, updated.text

    validation = await client.post(
        f"{created['base_url']}/draft/validation-runs", json={}
    )
    assert validation.status_code == 201, validation.text
    assert validation.json()["data"]["valid"] is True
    published = await client.post(
        f"{created['base_url']}/versions",
        json={
            "reason": "Fix Canvas recipe",
            "expectedRevision": 2,
            "validationRunId": validation.json()["data"]["runId"],
        },
    )

    assert published.status_code == 201, published.text
    params = published.json()["data"]["graph"]["nodes"][0]["params"]
    assert params == {"canvasSnapshotId": snapshot.id}
