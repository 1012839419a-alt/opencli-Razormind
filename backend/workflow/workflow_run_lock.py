"""Cross-dialect lock for freshness-sensitive workflow-run transactions."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.workflow_run import WorkflowRun


async def lock_scoped_workflow_run(
    db: AsyncSession,
    *,
    workflow_id: str,
    studio_workflow_version_id: str,
    run_id: str,
) -> WorkflowRun | None:
    """Lock a run before any freshness-sensitive read.

    PostgreSQL uses a row write lock. SQLite ignores ``FOR UPDATE``, so a
    no-op update of the same row acquires its transaction-wide write barrier
    without changing the persisted run projection.
    """
    filters = (
        WorkflowRun.id == run_id,
        WorkflowRun.workflow_id == workflow_id,
        WorkflowRun.studio_workflow_version_id == studio_workflow_version_id,
    )
    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        result = await db.execute(
            update(WorkflowRun).where(*filters).values(updated_at=WorkflowRun.updated_at)
        )
        if result.rowcount != 1:
            return None
        return await db.scalar(select(WorkflowRun).where(*filters))
    return await db.scalar(select(WorkflowRun).where(*filters).with_for_update())
