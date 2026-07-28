import pytest
from sqlalchemy import select

from backend.models.image_studio import ImageGenerationJob
from backend.models.studio import StudioProject, StudioWorkflow, StudioWorkspace
from backend.services import image_studio_service
from backend.workflow.async_orchestrator import image_generation_execution_key


def _image_workflow() -> dict:
    return {
        "id": "image-workflow",
        "name": "Image Workflow",
        "profile": "intelligence",
        "version": 1,
        "nodes": [
            {
                "id": "generate-hero",
                "kind": "media",
                "capability": "generate",
                "params": {"canvasSnapshotId": "snapshot-v1"},
                "ui": {"catalogId": "media.image-generation"},
            },
            {
                "id": "downstream-normalize",
                "kind": "agent",
                "capability": "normalize",
                "params": {},
            },
        ],
        "edges": [
            {
                "id": "image-to-downstream",
                "source": "generate-hero",
                "target": "downstream-normalize",
                "sourcePort": "assets",
                "targetPort": "records",
            }
        ],
    }


@pytest.mark.asyncio
async def test_image_generation_waits_then_resumes_once_with_monotonic_events(client) -> None:
    started = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": _image_workflow(),
            "runId": "run-image-1",
            "traceId": "trace-image-1",
        },
    )

    assert started.status_code == 202
    projection = started.json()["data"]
    assert projection["status"] == "waiting"
    states = {state["nodeId"]: state for state in projection["nodeStates"]}
    assert states["generate-hero"]["status"] == "waiting"
    assert states["downstream-normalize"]["status"] == "queued"

    checkpoint = (
        await client.get("/api/v1/workflows/runs/run-image-1/checkpoint")
    ).json()["data"]
    assert checkpoint["waitingNodeIds"] == ["generate-hero"]
    pending = checkpoint["pendingJobs"][0]
    assert pending["nodeId"] == "generate-hero"
    assert pending["attempt"] == 1
    assert pending["idempotencyKey"]

    rejected = await client.post(
        "/api/v1/workflows/runs/run-image-1/source-outputs",
        json={
            "sourceOutputs": {
                "generate-hero": [
                    {
                        "id": "asset-generated-1",
                        "type": "mediaAsset",
                        "mimeType": "image/png",
                    }
                ]
            }
        },
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == (
        "Image generation outputs are accepted only from the platform job worker"
    )

    events = (
        await client.get("/api/v1/workflows/runs/run-image-1/events")
    ).json()["data"]
    sequences = [event["sequence"] for event in events]
    assert sequences == list(range(1, len(events) + 1))
    waiting_events = [
        event
        for event in events
        if event["nodeId"] == "generate-hero" and event["eventType"] == "waiting"
    ]
    assert len(waiting_events) == 1
    assert waiting_events[0]["details"]["canvasSnapshotId"] == "snapshot-v1"
    assert all(
        event["eventType"] != "partial" or event["nodeId"] != "generate-hero"
        for event in events
    )


@pytest.mark.asyncio
async def test_image_asset_node_emits_fixed_assets_without_generation(client) -> None:
    project = _image_workflow()
    project["nodes"] = [
        {
            "id": "select-logo",
            "kind": "media",
            "capability": "fetch",
            "params": {"assetIds": ["asset-logo"]},
            "ui": {"catalogId": "media.image-asset"},
        }
    ]
    project["edges"] = []

    started = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-image-asset-1",
            "traceId": "trace-image-asset-1",
        },
    )

    assert started.status_code == 202
    assert started.json()["data"]["status"] == "completed"
    events = (
        await client.get("/api/v1/workflows/runs/run-image-asset-1/events")
    ).json()["data"]
    partial = next(event for event in events if event["eventType"] == "partial")
    assert partial["details"]["bindingId"] == "workflow.media.image-asset"
    assert partial["details"]["assetIds"] == ["asset-logo"]
    assert all(event["eventType"] != "waiting" for event in events)


@pytest.mark.asyncio
async def test_waiting_image_node_materializes_one_durable_job_in_the_run_transaction(
    client, db_session
) -> None:
    workspace = StudioWorkspace(name="Runtime Workspace", slug="runtime-workspace")
    db_session.add(workspace)
    await db_session.flush()
    studio_project = StudioProject(
        workspace_id=workspace.id,
        name="Runtime Project",
        slug="runtime-project",
        app_type="workflow",
        created_by_user_id="test-user",
    )
    db_session.add(studio_project)
    await db_session.flush()
    workflow = StudioWorkflow(project_id=studio_project.id, name="Runtime Workflow")
    db_session.add(workflow)
    await db_session.flush()
    document = await image_studio_service.create_document(
        db_session,
        workspace_id=workspace.id,
        project_id=studio_project.id,
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

    run_id = "00000000-0000-4000-8000-000000000001"
    project = _image_workflow()
    project["id"] = workflow.id
    project["nodes"][0]["params"]["canvasSnapshotId"] = snapshot.id

    started = await client.post(
        "/api/v1/workflows/runs",
        json={"project": project, "runId": run_id, "traceId": "trace-durable-job"},
    )

    assert started.status_code == 202, started.text
    execution_key = image_generation_execution_key(run_id, "generate-hero", 1)
    job = await db_session.scalar(
        select(ImageGenerationJob).where(ImageGenerationJob.id == execution_key.job_id)
    )
    assert job is not None
    assert job.snapshot_id == snapshot.id
    assert job.idempotency_key == execution_key.idempotency_key
    assert job.status == "blocked"
    assert job.error_code == "image-runtime-disabled"
