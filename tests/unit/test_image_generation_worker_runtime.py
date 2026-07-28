from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from backend.image_studio.job_runner import JobRunnerResult
from backend.image_studio.worker_runtime import (
    dispatch_block_reason,
    drive_image_generation_job,
)


@dataclass
class FakeJob:
    id: str = "job-1"
    status: str = "queued"
    error_code: str | None = None
    invoke_queue_item_id: str | None = None


class FakeRunner:
    def __init__(self, *, submit: JobRunnerResult | None = None, reconcile=None) -> None:
        self.submit_result = submit or JobRunnerResult(
            status="submitted",
            invoke_batch_id="batch-1",
            invoke_queue_item_id="queue-1",
            invoke_session_id="session-1",
        )
        self.reconcile_result = reconcile or JobRunnerResult(status="running")
        self.calls: list[str] = []

    async def submit(self, job, snapshot) -> JobRunnerResult:
        self.calls.append("submit")
        return self.submit_result

    async def reconcile(self, job) -> JobRunnerResult:
        self.calls.append("reconcile")
        return self.reconcile_result

    async def retry_ingest(self, job) -> JobRunnerResult:
        self.calls.append("retry_ingest")
        return self.reconcile_result


class FailingSubmitRunner(FakeRunner):
    async def submit(self, job, snapshot) -> JobRunnerResult:
        self.calls.append("submit")
        raise RuntimeError("http://invokeai:9090 bearer private-secret")


def test_dispatch_fails_closed_unless_sidecar_and_celery_are_both_enabled() -> None:
    assert dispatch_block_reason(
        SimpleNamespace(invokeai_enabled=False, task_executor="celery")
    ) == "image-runtime-disabled"
    assert dispatch_block_reason(
        SimpleNamespace(invokeai_enabled=True, task_executor="local")
    ) == "durable-worker-required"
    assert dispatch_block_reason(
        SimpleNamespace(invokeai_enabled=True, task_executor="celery")
    ) is None


async def test_queued_job_persists_sidecar_mapping_before_durable_poll() -> None:
    events: list[tuple[str, Any]] = []
    job = FakeJob()
    runner = FakeRunner()

    async def persist(result: JobRunnerResult) -> None:
        events.append(("persist", result.to_updates()))
        job.status = result.status
        job.invoke_queue_item_id = result.invoke_queue_item_id

    async def load_assets(_ids):
        raise AssertionError("assets are only loaded after ingest succeeds")

    def schedule_poll(job_id: str) -> None:
        events.append(("poll", job_id))

    def schedule_resume(*_args) -> None:
        raise AssertionError("workflow cannot resume before asset ingest")

    outcome = await drive_image_generation_job(
        job,
        object(),
        runner,
        persist_result=persist,
        load_assets=load_assets,
        schedule_poll=schedule_poll,
        schedule_resume=schedule_resume,
    )

    assert runner.calls == ["submit"]
    assert outcome == "poll_scheduled"
    assert events[0][0] == "persist"
    assert events[0][1]["invoke_queue_item_id"] == "queue-1"
    assert events[1] == ("poll", "job-1")


async def test_running_job_resumes_workflow_only_after_assets_are_persisted() -> None:
    events: list[tuple[str, Any]] = []
    job = FakeJob(status="running", invoke_queue_item_id="queue-1")
    runner = FakeRunner(
        reconcile=JobRunnerResult(
            status="succeeded",
            invoke_queue_item_id="queue-1",
            output_asset_ids=("asset-1",),
        )
    )

    async def persist(result: JobRunnerResult) -> None:
        events.append(("commit", result.status, result.output_asset_ids))
        job.status = result.status

    async def load_assets(asset_ids):
        events.append(("load", tuple(asset_ids)))
        return [{"id": "asset-1", "type": "mediaAsset", "mimeType": "image/png"}]

    def schedule_resume(run_id: str, node_id: str, assets: list[dict]) -> None:
        events.append(("resume", run_id, node_id, assets))

    # The minimal fake only needs these identifiers for the resume boundary.
    job.run_id = "run-1"
    job.node_id = "image-node"

    outcome = await drive_image_generation_job(
        job,
        object(),
        runner,
        persist_result=persist,
        load_assets=load_assets,
        schedule_poll=lambda _job_id: events.append(("unexpected-poll",)),
        schedule_resume=schedule_resume,
    )

    assert outcome == "workflow_resume_scheduled"
    assert runner.calls == ["reconcile"]
    assert [event[0] for event in events] == ["commit", "load", "resume"]
    assert events[-1][3][0]["id"] == "asset-1"


async def test_retryable_ingest_never_resubmits_generation() -> None:
    events: list[str] = []
    job = FakeJob(
        status="failed",
        error_code="retryable-ingest",
        invoke_queue_item_id="queue-1",
    )
    job.run_id = "run-1"
    job.node_id = "image-node"
    runner = FakeRunner(
        reconcile=JobRunnerResult(
            status="succeeded",
            invoke_queue_item_id="queue-1",
            output_asset_ids=("asset-1",),
        )
    )

    async def persist(result: JobRunnerResult) -> None:
        events.append(f"persist:{result.status}")

    await drive_image_generation_job(
        job,
        object(),
        runner,
        persist_result=persist,
        load_assets=lambda _ids: _async_value([{"id": "asset-1"}]),
        schedule_poll=lambda _job_id: events.append("poll"),
        schedule_resume=lambda *_args: events.append("resume"),
    )

    assert runner.calls == ["retry_ingest"]
    assert "submit" not in runner.calls
    assert events == ["persist:succeeded", "resume"]


async def test_submit_failure_is_blocked_without_exposing_sidecar_or_secret() -> None:
    persisted: list[JobRunnerResult] = []

    async def persist(result: JobRunnerResult) -> None:
        persisted.append(result)

    outcome = await drive_image_generation_job(
        FakeJob(),
        object(),
        FailingSubmitRunner(),
        persist_result=persist,
        load_assets=lambda _ids: _async_value([]),
        schedule_poll=lambda _job_id: None,
        schedule_resume=lambda *_args: None,
    )

    assert outcome == "terminal"
    assert persisted[0].status == "blocked"
    assert persisted[0].error_code == "invoke-submit-failed"
    assert "invokeai" not in str(persisted[0].to_updates()).lower()
    assert "private-secret" not in str(persisted[0].to_updates())


async def _async_value(value):
    return value
