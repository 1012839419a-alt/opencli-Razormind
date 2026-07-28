import struct
import zlib

import pytest

from backend.models.image_studio import ImageGenerationJobStatus
from backend.schemas.workflow import WorkflowRunStartRequest
from backend.services import image_studio_service
from backend.workflow.async_orchestrator import image_generation_execution_key
from backend.workflow.opencli_hda_tracer import start_workflow_run


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type + payload).to_bytes(4, "big")
    return len(payload).to_bytes(4, "big") + chunk_type + payload + checksum


def test_image_ingest_uses_magic_dimensions_and_removes_png_exif():
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 12, 8, 8, 6, 0, 0, 0))
        + _png_chunk(b"eXIf", b"private-camera-metadata")
        + _png_chunk(b"IEND", b"")
    )

    sanitized, mime_type, width, height, extension = (
        image_studio_service.inspect_and_sanitize_image(png)
    )

    assert mime_type == "image/png"
    assert (width, height, extension) == (12, 8, "png")
    assert b"private-camera-metadata" not in sanitized


def test_image_ingest_rejects_unknown_magic_and_pixel_bombs():
    with pytest.raises(image_studio_service.MediaAssetValidationError):
        image_studio_service.inspect_and_sanitize_image(b"not-an-image")

    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 10000, 10000, 8, 6, 0, 0, 0))
        + _png_chunk(b"IEND", b"")
    )
    with pytest.raises(image_studio_service.MediaAssetValidationError):
        image_studio_service.inspect_and_sanitize_image(png)


async def _studio_scope(db_session):
    from backend.models.studio import StudioProject, StudioWorkflow, StudioWorkspace

    workspace = StudioWorkspace(name="Workspace", slug="image-studio-unit")
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


async def _waiting_image_run(db_session, workflow, snapshot, run_id="run-1"):
    await start_workflow_run(
        WorkflowRunStartRequest.model_validate(
            {
                "project": {
                    "id": workflow.id,
                    "name": "Image Workflow",
                    "profile": "intelligence",
                    "version": 1,
                    "nodes": [
                        {
                            "id": snapshot.node_id,
                            "kind": "media",
                            "capability": "generate",
                            "params": {"canvasSnapshotId": snapshot.id},
                            "ui": {"catalogId": "media.image-generation"},
                        }
                    ],
                },
                "runId": run_id,
                "traceId": f"trace-{run_id}",
            }
        ),
        session=db_session,
    )
    return image_generation_execution_key(run_id, snapshot.node_id, 1)


@pytest.mark.asyncio
async def test_canvas_document_uses_optimistic_revision_lock(db_session):
    workspace, project, workflow = await _studio_scope(db_session)
    document = await image_studio_service.create_document(
        db_session,
        workspace_id=workspace.id,
        project_id=project.id,
        workflow_id=workflow.id,
        node_id="image-node",
        document={"layers": []},
        updated_by_user_id="test-user",
    )

    saved = await image_studio_service.save_document(
        db_session,
        document=document,
        expected_revision=1,
        payload={"layers": [{"id": "layer-1"}]},
        updated_by_user_id="test-user",
    )
    assert saved.revision == 2

    with pytest.raises(image_studio_service.RevisionConflictError):
        await image_studio_service.save_document(
            db_session,
            document=document,
            expected_revision=1,
            payload={"layers": []},
            updated_by_user_id="test-user",
        )


@pytest.mark.asyncio
async def test_snapshot_is_a_frozen_copy_with_asset_and_model_provenance(db_session):
    workspace, project, workflow = await _studio_scope(db_session)
    document = await image_studio_service.create_document(
        db_session,
        workspace_id=workspace.id,
        project_id=project.id,
        workflow_id=workflow.id,
        node_id="image-node",
        document={"layers": [{"id": "layer-1"}]},
        updated_by_user_id="test-user",
    )
    asset = await image_studio_service.import_asset(
        db_session,
        workspace_id=workspace.id,
        project_id=project.id,
        sha256="a" * 64,
        width=64,
        height=32,
        mime_type="image/png",
        storage_key="workspaces/ws/assets/a.png",
        provenance={"source": "upload"},
    )

    snapshot = await image_studio_service.create_snapshot(
        db_session,
        document=document,
        expected_revision=1,
        executable_graph={"nodes": {"noise": {"type": "rand_int"}}},
        model_fingerprint="sha256:model",
        seed=42,
        lora_revisions=[{"key": "detail", "revision": "v2"}],
        asset_ids=[asset.id],
        created_by_user_id="test-user",
    )
    document.document = {"layers": []}
    document.revision = 2
    await db_session.flush()

    assert snapshot.document_revision == 1
    assert snapshot.canvas_document == {"layers": [{"id": "layer-1"}]}
    assert snapshot.asset_ids == [asset.id]
    assert snapshot.model_fingerprint == "sha256:model"


@pytest.mark.asyncio
async def test_generation_job_is_idempotent_and_enforces_state_machine(db_session):
    workspace, project, workflow = await _studio_scope(db_session)
    document = await image_studio_service.create_document(
        db_session,
        workspace_id=workspace.id,
        project_id=project.id,
        workflow_id=workflow.id,
        node_id="image-node",
        document={"layers": []},
        updated_by_user_id="test-user",
    )
    snapshot = await image_studio_service.create_snapshot(
        db_session,
        document=document,
        expected_revision=1,
        executable_graph={"nodes": {}},
        model_fingerprint="sha256:model",
        seed=7,
        lora_revisions=[],
        asset_ids=[],
        created_by_user_id="test-user",
    )
    execution_key = await _waiting_image_run(db_session, workflow, snapshot)

    with pytest.raises(image_studio_service.ImageStudioConflictError):
        await image_studio_service.create_job(
            db_session,
            snapshot=snapshot,
            run_id="run-1",
            node_id="image-node",
            attempt=1,
            idempotency_key="client-selected-key",
        )

    first = await image_studio_service.create_job(
        db_session,
        snapshot=snapshot,
        run_id="run-1",
        node_id="image-node",
        attempt=1,
        idempotency_key=execution_key.idempotency_key,
    )
    duplicate = await image_studio_service.create_job(
        db_session,
        snapshot=snapshot,
        run_id="run-1",
        node_id="image-node",
        attempt=1,
        idempotency_key=execution_key.idempotency_key,
    )
    assert first.id == duplicate.id
    assert first.id == execution_key.job_id
    assert first.run_id == "run-1"
    assert first.attempt == 1
    assert first.status == ImageGenerationJobStatus.QUEUED.value

    for target in (
        ImageGenerationJobStatus.SUBMITTED,
        ImageGenerationJobStatus.RUNNING,
        ImageGenerationJobStatus.INGESTING,
        ImageGenerationJobStatus.SUCCEEDED,
    ):
        await image_studio_service.transition_job(db_session, first, target)
    assert first.status == ImageGenerationJobStatus.SUCCEEDED.value

    with pytest.raises(image_studio_service.InvalidJobTransitionError):
        await image_studio_service.transition_job(
            db_session, first, ImageGenerationJobStatus.RUNNING
        )


@pytest.mark.asyncio
async def test_generation_job_requires_a_persisted_workflow_run(db_session):
    workspace, project, workflow = await _studio_scope(db_session)
    document = await image_studio_service.create_document(
        db_session,
        workspace_id=workspace.id,
        project_id=project.id,
        workflow_id=workflow.id,
        node_id="image-node",
        document={"layers": []},
        updated_by_user_id="test-user",
    )
    snapshot = await image_studio_service.create_snapshot(
        db_session,
        document=document,
        expected_revision=1,
        executable_graph={"nodes": {}},
        model_fingerprint="sha256:model",
        seed=7,
        lora_revisions=[],
        asset_ids=[],
        created_by_user_id="test-user",
    )
    execution_key = image_generation_execution_key("missing-run", "image-node", 1)

    with pytest.raises(image_studio_service.ImageStudioNotFoundError):
        await image_studio_service.create_job(
            db_session,
            snapshot=snapshot,
            run_id="missing-run",
            node_id="image-node",
            attempt=1,
            idempotency_key=execution_key.idempotency_key,
        )


@pytest.mark.asyncio
async def test_canvas_preview_job_uses_snapshot_scoped_run_identity(db_session):
    workspace, project, workflow = await _studio_scope(db_session)
    document = await image_studio_service.create_document(
        db_session,
        workspace_id=workspace.id,
        project_id=project.id,
        workflow_id=workflow.id,
        node_id="image-node",
        document={"layers": []},
        updated_by_user_id="test-user",
    )
    snapshot = await image_studio_service.create_snapshot(
        db_session,
        document=document,
        expected_revision=1,
        executable_graph={"nodes": {}},
        model_fingerprint="sha256:model",
        seed=7,
        lora_revisions=[],
        asset_ids=[],
        created_by_user_id="test-user",
    )

    preview = await image_studio_service.create_job(
        db_session,
        snapshot=snapshot,
        run_id=snapshot.id,
        node_id="image-node",
        attempt=1,
        idempotency_key="preview-request-1",
        mode="preview",
    )

    assert preview.run_id == snapshot.id
    with pytest.raises(image_studio_service.ImageStudioConflictError):
        await image_studio_service.create_job(
            db_session,
            snapshot=snapshot,
            run_id="foreign-snapshot",
            node_id="image-node",
            attempt=1,
            idempotency_key="preview-request-2",
            mode="preview",
        )


@pytest.mark.asyncio
async def test_generation_job_requires_the_node_to_be_waiting(db_session):
    from backend.models.workflow_run import WorkflowRun

    workspace, project, workflow = await _studio_scope(db_session)
    document = await image_studio_service.create_document(
        db_session,
        workspace_id=workspace.id,
        project_id=project.id,
        workflow_id=workflow.id,
        node_id="image-node",
        document={"layers": []},
        updated_by_user_id="test-user",
    )
    snapshot = await image_studio_service.create_snapshot(
        db_session,
        document=document,
        expected_revision=1,
        executable_graph={"nodes": {}},
        model_fingerprint="sha256:model",
        seed=7,
        lora_revisions=[],
        asset_ids=[],
        created_by_user_id="test-user",
    )
    execution_key = await _waiting_image_run(
        db_session, workflow, snapshot, run_id="run-completed"
    )
    workflow_run = await db_session.get(WorkflowRun, "run-completed")
    assert workflow_run is not None
    workflow_run.status = "completed"
    workflow_run.projection = {
        **workflow_run.projection,
        "status": "completed",
        "nodeStates": [
            {**state, "status": "completed"}
            for state in workflow_run.projection["nodeStates"]
        ],
    }
    await db_session.flush()

    with pytest.raises(image_studio_service.ImageStudioConflictError):
        await image_studio_service.create_job(
            db_session,
            snapshot=snapshot,
            run_id="run-completed",
            node_id="image-node",
            attempt=1,
            idempotency_key=execution_key.idempotency_key,
        )


@pytest.mark.asyncio
async def test_generation_job_requires_matching_persisted_checkpoint_identity(db_session):
    from sqlalchemy import select

    from backend.models.workflow_run import WorkflowRunEvent

    workspace, project, workflow = await _studio_scope(db_session)
    document = await image_studio_service.create_document(
        db_session,
        workspace_id=workspace.id,
        project_id=project.id,
        workflow_id=workflow.id,
        node_id="image-node",
        document={"layers": []},
        updated_by_user_id="test-user",
    )
    snapshot = await image_studio_service.create_snapshot(
        db_session,
        document=document,
        expected_revision=1,
        executable_graph={"nodes": {}},
        model_fingerprint="sha256:model",
        seed=7,
        lora_revisions=[],
        asset_ids=[],
        created_by_user_id="test-user",
    )
    execution_key = await _waiting_image_run(
        db_session, workflow, snapshot, run_id="run-tampered-checkpoint"
    )
    event = await db_session.scalar(
        select(WorkflowRunEvent).where(
            WorkflowRunEvent.run_id == "run-tampered-checkpoint",
            WorkflowRunEvent.node_id == "image-node",
            WorkflowRunEvent.event_type == "waiting",
        )
    )
    assert event is not None
    event.payload = {
        **event.payload,
        "details": {**event.payload["details"], "jobId": "foreign-job"},
    }
    await db_session.flush()

    with pytest.raises(image_studio_service.ImageStudioConflictError):
        await image_studio_service.create_job(
            db_session,
            snapshot=snapshot,
            run_id="run-tampered-checkpoint",
            node_id="image-node",
            attempt=1,
            idempotency_key=execution_key.idempotency_key,
        )


@pytest.mark.asyncio
async def test_workflow_resume_revalidates_job_and_rebuilds_scoped_assets(db_session):
    workspace, project, workflow = await _studio_scope(db_session)
    document = await image_studio_service.create_document(
        db_session,
        workspace_id=workspace.id,
        project_id=project.id,
        workflow_id=workflow.id,
        node_id="image-node",
        document={"layers": []},
        updated_by_user_id="test-user",
    )
    snapshot = await image_studio_service.create_snapshot(
        db_session,
        document=document,
        expected_revision=1,
        executable_graph={"nodes": {}},
        model_fingerprint="sha256:model",
        seed=7,
        lora_revisions=[],
        asset_ids=[],
        created_by_user_id="test-user",
    )
    execution_key = await _waiting_image_run(
        db_session, workflow, snapshot, run_id="run-resume"
    )
    job = await image_studio_service.create_job(
        db_session,
        snapshot=snapshot,
        run_id="run-resume",
        node_id="image-node",
        attempt=1,
        idempotency_key=execution_key.idempotency_key,
    )
    asset = await image_studio_service.import_asset(
        db_session,
        workspace_id=workspace.id,
        project_id=project.id,
        sha256="b" * 64,
        width=128,
        height=64,
        mime_type="image/png",
        storage_key="workspaces/ws/assets/generated.png",
        provenance={"source": "invokeai"},
    )
    for target in (
        ImageGenerationJobStatus.SUBMITTED,
        ImageGenerationJobStatus.RUNNING,
        ImageGenerationJobStatus.INGESTING,
        ImageGenerationJobStatus.SUCCEEDED,
    ):
        await image_studio_service.transition_job(
            db_session,
            job,
            target,
            output_asset_ids=[asset.id] if target == ImageGenerationJobStatus.SUCCEEDED else None,
        )

    with pytest.raises(image_studio_service.ImageStudioConflictError):
        await image_studio_service.prepare_workflow_image_resume(
            db_session,
            job_id=job.id,
            run_id="run-resume",
            node_id="image-node",
            assets=[{"id": "foreign-asset"}],
        )

    canonical_assets = await image_studio_service.prepare_workflow_image_resume(
        db_session,
        job_id=job.id,
        run_id="run-resume",
        node_id="image-node",
        assets=[{"id": asset.id, "contentUrl": "https://attacker.invalid/image.png"}],
    )

    assert canonical_assets == [
        {
            "id": asset.id,
            "type": "mediaAsset",
            "mimeType": "image/png",
            "width": 128,
            "height": 64,
            "contentUrl": asset.content_url,
            "provenance": {"source": "invokeai"},
        }
    ]


@pytest.mark.asyncio
async def test_only_retryable_ingest_failure_can_reenter_ingesting(db_session):
    retryable = image_studio_service.ImageGenerationJob(
        status=ImageGenerationJobStatus.FAILED.value,
        error_code="retryable-ingest",
        invoke_queue_item_id="queue-1",
        output_asset_ids=["asset-a"],
    )
    await image_studio_service.retry_ingest_job(db_session, retryable)
    assert retryable.status == ImageGenerationJobStatus.INGESTING.value
    assert retryable.output_asset_ids == ["asset-a"]

    terminal = image_studio_service.ImageGenerationJob(
        status=ImageGenerationJobStatus.FAILED.value,
        error_code="invoke-generation-failed",
        invoke_queue_item_id="queue-2",
        output_asset_ids=[],
    )
    with pytest.raises(image_studio_service.InvalidJobTransitionError):
        await image_studio_service.retry_ingest_job(db_session, terminal)


def test_model_catalog_projects_only_hashed_main_models_and_marks_missing():
    catalog = image_studio_service.project_model_catalog(
        {
            "models": [
                {
                    "key": "main-1",
                    "name": "Main One",
                    "base": "sdxl",
                    "type": "main",
                    "hash": "sha256:main-one",
                },
                {
                    "key": "lora-1",
                    "name": "LoRA",
                    "base": "sdxl",
                    "type": "lora",
                    "hash": "sha256:lora",
                },
                {"key": "unhashed", "name": "Unsafe", "type": "main"},
            ]
        },
        {"models": [{"key": "main-1"}]},
    )

    assert catalog == [
        {
            "key": "main-1",
            "name": "Main One",
            "base": "sdxl",
            "type": "main",
            "fingerprint": "sha256:main-one",
            "available": False,
        }
    ]
