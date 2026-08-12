"""Creation and inspection of durable Gaojixing collection intent."""

from __future__ import annotations

import json
from collections.abc import Callable
from inspect import isawaitable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import queue_after_commit
from backend.models.gaojixing_collection import (
    GAOJIXING_GLOBAL_LEASE_ID,
    GaojixingCollectionRun,
    GaojixingCollectionRunStatus,
    GaojixingQuestionCheckpoint,
    GaojixingQuestionStatus,
    GaojixingRuntimeLease,
)
from backend.workflow.managed_gaojixing_question_batches import (
    resolve_managed_question_batch,
)

DispatchCallback = Callable[[str], Any]


class GaojixingCollectionConflictError(ValueError):
    """A workflow Run is already bound to different collection intent."""


async def ensure_collection(
    session: AsyncSession,
    *,
    workflow_run_id: str,
    node_id: str,
    question_batch_ref: str,
    dispatch: DispatchCallback | None = None,
    storage_root: Path | str | None = None,
    signing_key: str | None = None,
) -> GaojixingCollectionRun:
    """Idempotently freeze checkpoints and publish work only after commit."""

    resolved = resolve_managed_question_batch(
        question_batch_ref,
        expected_run_id=workflow_run_id,
        storage_root=storage_root,
        signing_key=signing_key,
    )
    existing = await session.scalar(
        select(GaojixingCollectionRun).where(
            GaojixingCollectionRun.workflow_run_id == workflow_run_id
        )
    )
    if existing is not None:
        _validate_existing_intent(
            existing,
            node_id=node_id,
            question_batch_ref=question_batch_ref,
            digest=resolved.digest,
        )
        return existing

    document = json.loads(resolved.question_bank_path.read_text(encoding="utf-8"))
    rows = [
        (phase, row)
        for phase in ("phase1", "phase2")
        for row in document.get(phase, [])
    ]
    candidate = GaojixingCollectionRun(
        workflow_run_id=workflow_run_id,
        node_id=node_id,
        question_batch_ref=question_batch_ref,
        question_bank_digest=resolved.digest,
    )
    try:
        async with session.begin_nested():
            session.add(candidate)
            await session.flush()
    except IntegrityError:
        job = await session.scalar(
            select(GaojixingCollectionRun).where(
                GaojixingCollectionRun.workflow_run_id == workflow_run_id
            )
        )
        if job is None:
            raise
        _validate_existing_intent(
            job,
            node_id=node_id,
            question_batch_ref=question_batch_ref,
            digest=resolved.digest,
        )
        return job
    job = candidate
    session.add_all(
        [
            GaojixingQuestionCheckpoint(
                collection_run_id=job.id,
                question_id=str(row["id"]),
                question=str(row["question"]),
                phase=phase,
                position=position,
            )
            for position, (phase, row) in enumerate(rows, start=1)
        ]
    )
    if await session.get(GaojixingRuntimeLease, GAOJIXING_GLOBAL_LEASE_ID) is None:
        try:
            async with session.begin_nested():
                session.add(GaojixingRuntimeLease(id=GAOJIXING_GLOBAL_LEASE_ID))
                await session.flush()
        except IntegrityError:
            if (
                await session.get(GaojixingRuntimeLease, GAOJIXING_GLOBAL_LEASE_ID)
                is None
            ):
                raise
    await session.flush()

    callback = dispatch or _dispatch_collection

    async def publish() -> None:
        result = callback(job.id)
        if isawaitable(result):
            await result

    queue_after_commit(session, publish)
    return job


def _validate_existing_intent(
    job: GaojixingCollectionRun,
    *,
    node_id: str,
    question_batch_ref: str,
    digest: str,
) -> None:
    if (
        job.question_bank_digest != digest
        or job.node_id != node_id
        or job.question_batch_ref != question_batch_ref
    ):
        raise GaojixingCollectionConflictError(
            "Workflow Run is already bound to another question collection"
        )


async def resume_collection(
    session: AsyncSession,
    *,
    job_id: str,
    dispatch: DispatchCallback | None = None,
) -> GaojixingCollectionRun | None:
    """Explicitly requeue a human-cleared checkpoint without permitting a new ask."""

    job = await session.scalar(
        select(GaojixingCollectionRun)
        .where(GaojixingCollectionRun.id == job_id)
        .with_for_update()
    )
    if job is None:
        return None
    if job.status not in {
        GaojixingCollectionRunStatus.WAITING_VERIFICATION.value,
        GaojixingCollectionRunStatus.WAITING_RECONCILIATION.value,
    }:
        raise GaojixingCollectionConflictError(
            "Gaojixing collection is not waiting for human recovery"
        )
    checkpoint = await session.scalar(
        select(GaojixingQuestionCheckpoint).where(
            GaojixingQuestionCheckpoint.collection_run_id == job.id,
            GaojixingQuestionCheckpoint.question_id == job.current_question_id,
        )
    )
    if checkpoint is None or checkpoint.status not in {
        GaojixingQuestionStatus.WAITING_VERIFICATION.value,
        GaojixingQuestionStatus.WAITING_RECONCILIATION.value,
    }:
        raise GaojixingCollectionConflictError(
            "Waiting collection has no matching resumable checkpoint"
        )
    checkpoint.status = GaojixingQuestionStatus.IN_PROGRESS.value
    job.status = GaojixingCollectionRunStatus.QUEUED.value
    job.waiting_kind = None
    job.waiting_artifact_ref = None
    job.lease_owner = None
    job.lease_fencing_token = None
    job.heartbeat_at = None
    job.lease_expires_at = None
    await session.flush()

    callback = dispatch or _dispatch_collection

    async def publish() -> None:
        result = callback(job.id)
        if isawaitable(result):
            await result

    queue_after_commit(session, publish)
    return job


async def mark_collection_succeeded(
    session: AsyncSession,
    *,
    workflow_run_id: str,
) -> bool:
    """Acknowledge that the same workflow Run committed HDA certification."""

    job = await session.scalar(
        select(GaojixingCollectionRun)
        .where(GaojixingCollectionRun.workflow_run_id == workflow_run_id)
        .with_for_update()
    )
    if job is None:
        return False
    if job.status == GaojixingCollectionRunStatus.SUCCEEDED.value:
        return True
    if job.status != GaojixingCollectionRunStatus.REVIEWING.value:
        return False
    from datetime import UTC, datetime

    job.status = GaojixingCollectionRunStatus.SUCCEEDED.value
    job.finished_at = datetime.now(UTC)
    await session.flush()
    return True


async def mark_collection_review_failed(
    session: AsyncSession,
    *,
    workflow_run_id: str,
    code: str,
) -> bool:
    """Persist a terminal HDA rejection after the same-run replay."""

    job = await session.scalar(
        select(GaojixingCollectionRun)
        .where(GaojixingCollectionRun.workflow_run_id == workflow_run_id)
        .with_for_update()
    )
    if job is None or job.status != GaojixingCollectionRunStatus.REVIEWING.value:
        return False
    from datetime import UTC, datetime

    job.status = GaojixingCollectionRunStatus.FAILED.value
    job.failure = {"code": code}
    job.finished_at = datetime.now(UTC)
    await session.flush()
    return True


async def _dispatch_collection(job_id: str) -> None:
    """Hand committed work to the configured local or Celery runtime."""

    from backend.workflow.gaojixing_worker_runtime import dispatch_collection_job

    dispatch_collection_job(job_id)


__all__ = [
    "GaojixingCollectionConflictError",
    "ensure_collection",
    "mark_collection_succeeded",
    "mark_collection_review_failed",
    "resume_collection",
]
