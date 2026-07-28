"""Durable ImageStudio worker wiring.

The pure ``drive_image_generation_job`` state machine is deliberately small and
dependency-injected.  The SQLAlchemy/InvokeAI composition lives below it so the
contract can be tested without Redis, a GPU sidecar, or real object storage.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal, Protocol

from sqlalchemy import select

from backend.config import Settings, get_settings
from backend.image_studio.adapter import InvokeAIAdapter
from backend.image_studio.invoke_client import InvokeAIClient, InvokeAIConnection
from backend.image_studio.job_runner import ImageGenerationJobRunner, JobRunnerResult
from backend.models.image_studio import CanvasSnapshot, ImageGenerationJob, MediaAsset
from backend.services import image_studio_service

WorkerOutcome = Literal[
    "poll_scheduled", "workflow_resume_scheduled", "terminal", "missing"
]


class _Runner(Protocol):
    async def submit(self, job: Any, snapshot: Any) -> JobRunnerResult: ...
    async def reconcile(self, job: Any) -> JobRunnerResult: ...
    async def retry_ingest(self, job: Any) -> JobRunnerResult: ...


def dispatch_block_reason(settings: Settings | Any) -> str | None:
    """Return a stable fail-closed reason for API-side dispatch gating."""

    if not settings.invokeai_enabled:
        return "image-runtime-disabled"
    if settings.task_executor != "celery":
        return "durable-worker-required"
    return None


async def drive_image_generation_job(
    job: Any,
    snapshot: Any,
    runner: _Runner,
    *,
    persist_result: Callable[[JobRunnerResult], Awaitable[None]],
    load_assets: Callable[[Sequence[str]], Awaitable[list[dict[str, Any]]]],
    schedule_poll: Callable[[str], None],
    schedule_resume: Callable[[str, str, list[dict[str, Any]]], None],
) -> WorkerOutcome:
    """Advance exactly one durable step and schedule only after persistence.

    A queued job submits once per durable idempotency identity. Pending states
    are polled by a later Celery delivery. A retryable ingest always reconciles
    the existing queue item and therefore never invokes ``submit``.
    """

    if job.status == "succeeded":
        assets = await load_assets(job.output_asset_ids)
        schedule_resume(job.run_id, job.node_id, assets)
        return "workflow_resume_scheduled"
    if job.status == "queued" or (
        job.status == "submitted" and not job.invoke_queue_item_id
    ):
        try:
            result = await runner.submit(job, snapshot)
        except Exception:
            # Sidecar/network errors can contain its private URL or token.
            result = JobRunnerResult(
                status="blocked",
                error_code="invoke-submit-failed",
                error_detail="Image runtime submission failed",
            )
    elif job.status == "failed" and job.error_code == "retryable-ingest":
        result = await runner.retry_ingest(job)
    elif job.status in {"submitted", "running", "ingesting"}:
        result = await runner.reconcile(job)
    else:
        return "terminal"

    # The callback contract includes the database commit. Nothing is queued
    # until the durable sidecar mapping/job state is visible to another worker.
    await persist_result(result)

    if result.status == "succeeded":
        assets = await load_assets(result.output_asset_ids)
        schedule_resume(job.run_id, job.node_id, assets)
        return "workflow_resume_scheduled"
    if result.status in {"submitted", "running", "ingesting"}:
        schedule_poll(job.id)
        return "poll_scheduled"
    return "terminal"


async def execute_image_generation_job(
    job_id: str,
    *,
    schedule_poll: Callable[[str], None],
    schedule_resume: Callable[[str, str, list[dict[str, Any]]], None],
    settings: Settings | None = None,
) -> WorkerOutcome:
    """Compose the real database, private adapter, asset store and workflow."""

    from backend.database import AsyncSessionLocal

    runtime_settings = settings or get_settings()
    if dispatch_block_reason(runtime_settings) is not None:
        return "terminal"

    async with AsyncSessionLocal() as db:
        job = await db.scalar(
            select(ImageGenerationJob)
            .where(ImageGenerationJob.id == job_id)
            .with_for_update()
        )
        if job is None:
            return "missing"
        snapshot = await db.scalar(
            select(CanvasSnapshot).where(CanvasSnapshot.id == job.snapshot_id)
        )
        if snapshot is None:
            await _persist_job_result(
                db,
                job,
                JobRunnerResult(
                    status="failed",
                    error_code="snapshot-not-found",
                    error_detail="Canvas snapshot is unavailable",
                ),
            )
            return "terminal"

        connection = InvokeAIConnection(
            base_url=runtime_settings.invokeai_base_url,
            jwt=runtime_settings.invokeai_api_token or None,
            timeout_seconds=runtime_settings.invokeai_request_timeout_seconds,
        )
        adapter = InvokeAIAdapter(InvokeAIClient(connection))

        async def checkpoint(result: JobRunnerResult) -> None:
            await _persist_job_result(db, job, result)

        async def ingest(
            *,
            workspace_id: str,
            project_id: str,
            image_name: str,
            chunks,
            provenance,
            **_scope,
        ) -> str:
            payload = bytearray()
            async for chunk in chunks:
                payload.extend(chunk)
                if len(payload) > image_studio_service.MAX_MEDIA_ASSET_BYTES:
                    raise image_studio_service.MediaAssetValidationError(
                        "Generated image exceeds platform limits"
                    )
            asset = await image_studio_service.import_asset_bytes(
                db,
                workspace_id=workspace_id,
                project_id=project_id,
                payload=bytes(payload),
                declared_mime_type=None,
                provenance=dict(provenance),
                filename=image_name,
            )
            await db.flush()
            return asset.id

        runner = ImageGenerationJobRunner(
            adapter, asset_ingestor=ingest, checkpoint=checkpoint
        )

        async def persist(result: JobRunnerResult) -> None:
            await _persist_job_result(db, job, result)

        async def load_assets(asset_ids: Sequence[str]) -> list[dict[str, Any]]:
            if not asset_ids:
                return []
            rows = (
                await db.execute(
                    select(MediaAsset).where(
                        MediaAsset.id.in_(list(asset_ids)),
                        MediaAsset.workspace_id == job.workspace_id,
                        MediaAsset.project_id == job.project_id,
                    )
                )
            ).scalars().all()
            by_id = {row.id: row for row in rows}
            return [_asset_output(by_id[asset_id]) for asset_id in asset_ids]

        return await drive_image_generation_job(
            job,
            snapshot,
            runner,
            persist_result=persist,
            load_assets=load_assets,
            schedule_poll=schedule_poll,
            schedule_resume=schedule_resume,
        )


async def cancel_image_generation_job(job_id: str) -> WorkerOutcome:
    """Ask the private sidecar to cancel and persist only its confirmation."""

    from backend.database import AsyncSessionLocal

    settings = get_settings()
    if dispatch_block_reason(settings) is not None:
        return "terminal"
    async with AsyncSessionLocal() as db:
        job = await db.scalar(
            select(ImageGenerationJob)
            .where(ImageGenerationJob.id == job_id)
            .with_for_update()
        )
        if job is None:
            return "missing"
        if job.status == "cancelled":
            return "terminal"
        if not job.invoke_queue_item_id:
            await _persist_job_result(db, job, JobRunnerResult(status="cancelled"))
            return "terminal"

        connection = InvokeAIConnection(
            base_url=settings.invokeai_base_url,
            jwt=settings.invokeai_api_token or None,
            timeout_seconds=settings.invokeai_request_timeout_seconds,
        )
        runner = ImageGenerationJobRunner(
            InvokeAIAdapter(InvokeAIClient(connection)),
            asset_ingestor=_unused_ingestor,
            checkpoint=_unused_checkpoint,
        )
        await _persist_job_result(db, job, await runner.cancel(job))
        return "terminal"


async def _persist_job_result(db, job, result: JobRunnerResult) -> None:
    for field, value in result.to_updates().items():
        setattr(job, field, value)
    await db.flush()
    await db.commit()


def _asset_output(asset: MediaAsset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "type": "mediaAsset",
        "mimeType": asset.mime_type,
        "width": asset.width,
        "height": asset.height,
        "contentUrl": asset.content_url,
        "provenance": dict(asset.provenance or {}),
    }


async def _unused_ingestor(**_kwargs) -> str:
    raise AssertionError("cancel must not ingest assets")


async def _unused_checkpoint(_result: JobRunnerResult) -> None:
    return None
