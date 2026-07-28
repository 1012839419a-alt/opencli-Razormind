from backend.schemas.workflow import WorkflowProject, WorkflowProjectNode
from backend.worker.tasks import (
    resume_workflow_image_generation,
    run_image_generation_job,
)
from backend.workflow.async_orchestrator import image_generation_execution_key
from backend.workflow.runtime_contracts import runtime_io_contract_manifest
from backend.workflow.runtime_registry import (
    IMAGE_ASSET_BINDING_ID,
    IMAGE_GENERATION_BINDING_ID,
    resolve_runtime_metadata,
)


def test_media_nodes_have_distinct_first_party_runtime_contracts() -> None:
    generation = WorkflowProjectNode(
        id="generate-hero",
        kind="media",
        capability="generate",
        params={"canvasSnapshotId": "snapshot-v1"},
        ui={"catalogId": "media.image-generation"},
    )
    asset = WorkflowProjectNode(
        id="select-logo",
        kind="media",
        capability="fetch",
        params={"assetIds": ["asset-logo"]},
        ui={"catalogId": "media.image-asset"},
    )

    generation_runtime = resolve_runtime_metadata(generation, None)
    asset_runtime = resolve_runtime_metadata(asset, None)

    assert generation_runtime["binding"]["binding_id"] == IMAGE_GENERATION_BINDING_ID
    assert generation_runtime["binding"]["input"]["canvasSnapshotId"] == "snapshot-v1"
    assert generation_runtime["binding"]["contract"]["inputShape"]["ports"] == [
        {"name": "prompt", "type": "text"},
        {"name": "assets", "type": "mediaAsset[]"},
    ]
    assert generation_runtime["binding"]["contract"]["outputShape"]["ports"] == [
        {"name": "assets", "type": "mediaAsset[]"},
        {"name": "generation", "type": "mediaGenerationResult"},
    ]
    assert asset_runtime["binding"]["binding_id"] == IMAGE_ASSET_BINDING_ID
    assert asset_runtime["binding"]["input"]["assetIds"] == ["asset-logo"]


def test_image_generation_execution_key_is_stable_per_attempt() -> None:
    first = image_generation_execution_key("run-1", "generate-hero", 1)
    duplicate = image_generation_execution_key("run-1", "generate-hero", 1)
    retry = image_generation_execution_key("run-1", "generate-hero", 2)

    assert first == duplicate
    assert first.idempotency_key != retry.idempotency_key
    assert first.job_id != retry.job_id
    assert first.as_details()["attempt"] == 1


def test_image_generation_contract_declares_waiting_checkpoint() -> None:
    contract = runtime_io_contract_manifest(IMAGE_GENERATION_BINDING_ID)

    assert contract is not None
    assert contract["status"] == "dispatch_only"
    assert "waiting" in contract["eventShape"]["events"]
    assert "canvasSnapshotId" in contract["configGate"]["required"]


def test_workflow_project_accepts_media_generate_and_media_fetch() -> None:
    project = WorkflowProject.model_validate(
        {
            "id": "image-workflow",
            "name": "Image Workflow",
            "profile": "intelligence",
            "nodes": [
                {
                    "id": "generate-hero",
                    "kind": "media",
                    "capability": "generate",
                    "params": {"canvasSnapshotId": "snapshot-v1"},
                    "ui": {"catalogId": "media.image-generation"},
                },
                {
                    "id": "select-logo",
                    "kind": "media",
                    "capability": "fetch",
                    "params": {"assetIds": ["asset-logo"]},
                    "ui": {"catalogId": "media.image-asset"},
                },
            ],
        }
    )

    assert [(node.kind, node.capability) for node in project.nodes] == [
        ("media", "generate"),
        ("media", "fetch"),
    ]


def test_celery_registers_the_image_generation_resume_boundary() -> None:
    assert resume_workflow_image_generation.name == "resume_workflow_image_generation"


def test_image_job_task_passes_job_identity_to_resume(monkeypatch) -> None:
    from backend.image_studio import worker_runtime

    resumed = []

    async def execute(job_id, *, schedule_poll, schedule_resume):
        assert job_id == "job-1"
        schedule_resume("run-1", "image-node", [{"id": "asset-1"}])
        return "succeeded"

    monkeypatch.setattr(worker_runtime, "execute_image_generation_job", execute)
    monkeypatch.setattr(
        resume_workflow_image_generation,
        "delay",
        lambda *args: resumed.append(args),
    )

    assert run_image_generation_job.run("job-1") == "succeeded"
    assert resumed == [("job-1", "run-1", "image-node", [{"id": "asset-1"}])]
