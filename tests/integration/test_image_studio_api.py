import base64
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.v1 import image_studio as image_studio_api
from backend.api.v1.image_studio import router
from backend.database import get_db
from backend.models import image_studio as _image_studio_models  # noqa: F401
from backend.models.studio import StudioProject, StudioWorkflow, StudioWorkspace


@pytest_asyncio.fixture
async def image_client(db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCLI_MEDIA_ROOT", str(tmp_path / "media"))
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _studio_scope(db_session, suffix="api"):
    workspace = StudioWorkspace(name=f"Workspace {suffix}", slug=f"image-{suffix}")
    db_session.add(workspace)
    await db_session.flush()
    project = StudioProject(
        workspace_id=workspace.id,
        name="Project",
        slug="project",
        app_type="workflow",
        created_by_user_id="test-user",
    )
    db_session.add(project)
    await db_session.flush()
    workflow = StudioWorkflow(project_id=project.id, name="Workflow")
    db_session.add(workflow)
    await db_session.flush()
    return workspace, project, workflow


def _base(workspace, project, workflow):
    return f"/api/v1/workspaces/{workspace.id}/projects/{project.id}/image-studio"


@pytest.mark.asyncio
async def test_document_save_contract_returns_409_for_stale_revision(
    image_client, db_session
):
    workspace, project, workflow = await _studio_scope(db_session)
    created = await image_client.post(
        f"{_base(workspace, project, workflow)}/documents",
        json={
            "workflowId": workflow.id,
            "nodeId": "image-node",
            "document": {"layers": []},
        },
    )
    assert created.status_code == 201, created.text
    document = created.json()["data"]
    assert document["revision"] == 1

    saved = await image_client.put(
        f"{_base(workspace, project, workflow)}/documents/{document['id']}",
        json={"expectedRevision": 1, "document": {"layers": [{"id": "layer-1"}]}},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["revision"] == 2

    stale = await image_client.put(
        f"{_base(workspace, project, workflow)}/documents/{document['id']}",
        json={"expectedRevision": 1, "document": {"layers": []}},
    )
    assert stale.status_code == 409

    loaded = await image_client.get(
        f"{_base(workspace, project, workflow)}/documents/{document['id']}"
    )
    assert loaded.status_code == 200
    assert loaded.json()["data"]["document"]["layers"][0]["id"] == "layer-1"


@pytest.mark.asyncio
async def test_snapshot_asset_and_job_contracts_are_workspace_scoped(
    image_client, db_session
):
    workspace, project, workflow = await _studio_scope(db_session, "owner")
    foreign_workspace, _, _ = await _studio_scope(db_session, "foreign")
    base = _base(workspace, project, workflow)

    document = (
        await image_client.post(
            f"{base}/documents",
            json={
                "workflowId": workflow.id,
                "nodeId": "image-node",
                "document": {"layers": []},
            },
        )
    ).json()["data"]
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    asset_response = await image_client.post(
        f"{base}/media-assets/import",
        files={"file": ("source.png", png, "image/png")},
        data={"provenance": '{"source":"upload"}'},
    )
    assert asset_response.status_code == 201, asset_response.text
    asset = asset_response.json()["data"]
    assert asset["width"] == 1
    assert asset["height"] == 1
    assert asset["filename"] == "source.png"
    assert "storageKey" not in asset
    content = await image_client.get(asset["contentUrl"])
    assert content.status_code == 200
    assert content.content == png
    assert content.headers["x-content-type-options"] == "nosniff"

    mismatched = await image_client.post(
        f"{base}/media-assets/import",
        files={"file": ("spoofed.jpg", png, "image/jpeg")},
    )
    assert mismatched.status_code == 422

    snapshot_response = await image_client.post(
        f"{base}/documents/{document['id']}/snapshots",
        json={
            "expectedRevision": 1,
            "executableGraph": {"nodes": {}},
            "modelFingerprint": "sha256:model",
            "seed": 42,
            "loraRevisions": [],
            "assetIds": [asset["id"]],
        },
    )
    assert snapshot_response.status_code == 201, snapshot_response.text
    snapshot = snapshot_response.json()["data"]

    job_response = await image_client.post(
        f"{base}/jobs",
        json={
            "mode": "preview",
            "snapshotId": snapshot["id"],
            "runId": snapshot["id"],
            "nodeId": "image-node",
            "attempt": 1,
            "idempotencyKey": "preview:image-node:1",
        },
    )
    assert job_response.status_code == 202, job_response.text
    job = job_response.json()["data"]
    assert job["status"] == "blocked"
    assert job["errorCode"] == "image-runtime-disabled"
    assert job["runId"] == snapshot["id"]
    assert job["attempt"] == 1

    events = await image_client.get(f"{base}/jobs/{job['id']}/events")
    assert events.status_code == 200
    assert '"type":"status"' in events.text

    models = await image_client.get(f"{base}/models")
    assert models.status_code == 200
    assert models.json()["data"] == []

    duplicate = await image_client.post(
        f"{base}/jobs",
        json={
            "mode": "preview",
            "snapshotId": snapshot["id"],
            "runId": snapshot["id"],
            "nodeId": "image-node",
            "attempt": 1,
            "idempotencyKey": "preview:image-node:1",
        },
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["data"]["id"] == job["id"]

    cancelled = await image_client.post(f"{base}/jobs/{job['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"

    listed = await image_client.get(
        f"{base}/media-assets"
    )
    assert [item["id"] for item in listed.json()["data"]] == [asset["id"]]

    hidden = await image_client.get(
        f"/api/v1/workspaces/{foreign_workspace.id}/projects/{project.id}"
        f"/image-studio/documents/{document['id']}"
    )
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_model_catalog_is_projected_without_exposing_sidecar_details(
    image_client, db_session, monkeypatch
):
    workspace, project, workflow = await _studio_scope(db_session, "models")
    monkeypatch.setattr(
        image_studio_api,
        "get_settings",
        lambda: SimpleNamespace(
            invokeai_enabled=True,
            invokeai_base_url="http://invoke.private:9090",
            invokeai_api_token="sidecar-secret",
            invokeai_request_timeout_seconds=30,
        ),
    )

    async def list_models(_self):
        return {
            "models": [
                {
                    "key": "model-1",
                    "name": "Model One",
                    "base": "sdxl",
                    "type": "main",
                    "hash": "sha256:model-one",
                    "path": "/private/model/path",
                }
            ]
        }

    async def list_missing_models(_self):
        return {"models": []}

    monkeypatch.setattr(image_studio_api.InvokeAIClient, "list_models", list_models)
    monkeypatch.setattr(
        image_studio_api.InvokeAIClient,
        "list_missing_models",
        list_missing_models,
    )

    response = await image_client.get(f"{_base(workspace, project, workflow)}/models")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == [
        {
            "key": "model-1",
            "name": "Model One",
            "base": "sdxl",
            "type": "main",
            "fingerprint": "sha256:model-one",
            "available": True,
        }
    ]
    serialized = response.text
    assert "sidecar-secret" not in serialized
    assert "invoke.private" not in serialized
    assert "/private/model/path" not in serialized
