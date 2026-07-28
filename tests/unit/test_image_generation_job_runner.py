from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from backend.image_studio.adapter import InvokeJobBinding, InvokeQueueState
from backend.image_studio.job_runner import ImageGenerationJobRunner, JobRunnerResult
from backend.models.image_studio import CanvasSnapshot, ImageGenerationJob


def _job(**overrides: Any) -> ImageGenerationJob:
    values = {
        "id": "job-1",
        "workspace_id": "workspace-1",
        "project_id": "project-1",
        "workflow_id": "workflow-1",
        "node_id": "image-node-1",
        "run_id": "run-1",
        "attempt": 2,
        "snapshot_id": "snapshot-1",
        "idempotency_key": "opencli-image:persisted-key",
        "status": "queued",
        "invoke_batch_id": None,
        "invoke_queue_item_id": None,
        "invoke_session_id": None,
        "output_asset_ids": [],
        "error_code": None,
        "error_detail": None,
    }
    values.update(overrides)
    return ImageGenerationJob(**values)


def _snapshot() -> CanvasSnapshot:
    return CanvasSnapshot(
        id="snapshot-1",
        workspace_id="workspace-1",
        project_id="project-1",
        workflow_id="workflow-1",
        node_id="image-node-1",
        document_id="document-1",
        document_revision=3,
        canvas_document={"layers": []},
        executable_graph={"id": "graph-1", "nodes": {"noise": {"type": "noise"}}},
        model_fingerprint="sdxl@sha256:abc",
        seed=7,
        lora_revisions=[],
        asset_ids=[],
        created_by_user_id="user-1",
    )


class FakeAdapter:
    def __init__(self) -> None:
        self.submit_calls = 0
        self.reconcile_calls = 0
        self.cancel_calls = 0
        self.reconcile_state = InvokeQueueState("running", "in_progress")
        self.stream_payloads = {"a.png": [b"a-", b"png"], "b.png": [b"b-png"]}
        self.submitted_graph: dict[str, Any] | None = None

    async def submit(
        self,
        binding: InvokeJobBinding,
        *,
        executable_graph: dict[str, Any],
        batch_data=(),
        runs: int = 1,
        prepend: bool = False,
    ) -> InvokeJobBinding:
        self.submit_calls += 1
        self.submitted_graph = executable_graph
        return binding.with_submission(
            queue_item_id="queue-41", batch_id="batch-7", session_id="session-9"
        )

    async def reconcile(self, binding: InvokeJobBinding, *, event_hint=None) -> InvokeQueueState:
        self.reconcile_calls += 1
        return self.reconcile_state

    async def cancel(self, binding: InvokeJobBinding) -> InvokeQueueState:
        self.cancel_calls += 1
        return InvokeQueueState("cancelled", "canceled")

    async def stream_image(self, image_name: str) -> AsyncIterator[bytes]:
        for chunk in self.stream_payloads[image_name]:
            yield chunk


async def test_submit_builds_binding_from_job_and_returns_persistable_sidecar_mapping():
    adapter = FakeAdapter()
    checkpoints: list[JobRunnerResult] = []

    async def checkpoint(result: JobRunnerResult) -> None:
        checkpoints.append(result)

    async def ingest(**kwargs) -> str:  # pragma: no cover - submit does not ingest
        raise AssertionError("ingest must not run")

    runner = ImageGenerationJobRunner(adapter, asset_ingestor=ingest, checkpoint=checkpoint)

    result = await runner.submit(_job(), _snapshot())

    assert adapter.submit_calls == 1
    assert adapter.submitted_graph == _snapshot().executable_graph
    assert result.status == "submitted"
    assert result.to_updates() == {
        "status": "submitted",
        "invoke_batch_id": "batch-7",
        "invoke_queue_item_id": "queue-41",
        "invoke_session_id": "session-9",
        "output_asset_ids": [],
        "error_code": None,
        "error_detail": None,
    }
    assert checkpoints == []


async def test_completed_queue_item_checkpoints_ingesting_then_streams_and_succeeds():
    adapter = FakeAdapter()
    adapter.reconcile_state = InvokeQueueState(
        "completed", "completed", image_names=("a.png", "b.png")
    )
    events: list[tuple[str, Any]] = []

    async def checkpoint(result: JobRunnerResult) -> None:
        events.append(("checkpoint", result.status))

    async def ingest(*, image_name: str, chunks: AsyncIterator[bytes], **scope) -> str:
        events.append(("ingest", image_name))
        assert scope == {
            "workspace_id": "workspace-1",
            "project_id": "project-1",
            "job_id": "job-1",
            "provenance": {
                "kind": "invokeai-generation",
                "jobId": "job-1",
                "snapshotId": "snapshot-1",
                "imageName": image_name,
            },
        }
        assert b"".join([chunk async for chunk in chunks]) in {b"a-png", b"b-png"}
        return {"a.png": "asset-a", "b.png": "asset-b"}[image_name]

    runner = ImageGenerationJobRunner(adapter, asset_ingestor=ingest, checkpoint=checkpoint)
    job = _job(
        status="running",
        invoke_queue_item_id="queue-41",
        invoke_batch_id="batch-7",
        invoke_session_id="session-9",
    )

    result = await runner.reconcile(job, event_hint={"status": "completed"})

    assert events == [
        ("checkpoint", "ingesting"),
        ("ingest", "a.png"),
        ("ingest", "b.png"),
    ]
    assert result.status == "succeeded"
    assert result.output_asset_ids == ("asset-a", "asset-b")
    assert "a.png" not in str(result.to_updates())


async def test_ingest_failure_is_retryable_without_resubmitting_generation_or_leaking_secret():
    adapter = FakeAdapter()
    adapter.reconcile_state = InvokeQueueState("completed", "completed", image_names=("a.png",))
    checkpoints: list[JobRunnerResult] = []
    ingest_attempts = 0
    sensitive_marker = "fixture-sensitive-value"

    async def checkpoint(result: JobRunnerResult) -> None:
        checkpoints.append(result)

    async def ingest(*, image_name: str, chunks: AsyncIterator[bytes], **scope) -> str:
        nonlocal ingest_attempts
        ingest_attempts += 1
        if ingest_attempts == 1:
            raise RuntimeError(f"object store rejected token {sensitive_marker}")
        return "asset-stable"

    runner = ImageGenerationJobRunner(adapter, asset_ingestor=ingest, checkpoint=checkpoint)
    first_job = _job(status="running", invoke_queue_item_id="queue-41")

    failed = await runner.reconcile(first_job)

    assert failed.status == "failed"
    assert failed.error_code == "retryable-ingest"
    assert sensitive_marker not in str(failed.to_updates())
    assert adapter.submit_calls == 0

    retry_job = _job(
        status="failed",
        invoke_queue_item_id="queue-41",
        error_code="retryable-ingest",
        error_detail=failed.error_detail,
    )
    succeeded = await runner.retry_ingest(retry_job)

    assert succeeded.status == "succeeded"
    assert succeeded.output_asset_ids == ("asset-stable",)
    assert adapter.submit_calls == 0
    assert adapter.reconcile_calls == 2
    assert ingest_attempts == 2


async def test_partial_ingest_retry_preserves_assets_and_skips_downloaded_images():
    adapter = FakeAdapter()
    adapter.reconcile_state = InvokeQueueState(
        "completed", "completed", image_names=("a.png", "b.png")
    )
    ingested: list[str] = []
    fail_second = True

    async def checkpoint(result: JobRunnerResult) -> None:
        pass

    async def ingest(*, image_name: str, chunks: AsyncIterator[bytes], **scope) -> str:
        nonlocal fail_second
        ingested.append(image_name)
        if image_name == "b.png" and fail_second:
            fail_second = False
            raise OSError("temporary store error")
        return f"asset-{image_name[0]}"

    runner = ImageGenerationJobRunner(adapter, asset_ingestor=ingest, checkpoint=checkpoint)
    failed = await runner.reconcile(_job(status="running", invoke_queue_item_id="queue-41"))
    assert failed.output_asset_ids == ("asset-a",)

    succeeded = await runner.retry_ingest(
        _job(
            status="failed",
            invoke_queue_item_id="queue-41",
            output_asset_ids=list(failed.output_asset_ids),
            error_code="retryable-ingest",
        )
    )

    assert ingested == ["a.png", "b.png", "b.png"]
    assert succeeded.output_asset_ids == ("asset-a", "asset-b")
    assert adapter.submit_calls == 0


async def test_cancel_calls_sidecar_for_submitted_job():
    adapter = FakeAdapter()

    async def checkpoint(result: JobRunnerResult) -> None:
        pass

    async def ingest(**kwargs) -> str:
        return "unused"

    runner = ImageGenerationJobRunner(adapter, asset_ingestor=ingest, checkpoint=checkpoint)
    result = await runner.cancel(_job(status="running", invoke_queue_item_id="queue-41"))

    assert adapter.cancel_calls == 1
    assert result.status == "cancelled"
    assert result.invoke_queue_item_id == "queue-41"
