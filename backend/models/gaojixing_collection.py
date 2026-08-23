from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import TimestampMixin


class GaojixingCollectionRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_VERIFICATION = "waiting_verification"
    WAITING_RECONCILIATION = "waiting_reconciliation"
    REVIEWING = "reviewing"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GaojixingQuestionStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CAPTURING = "capturing"
    PASSED = "passed"
    WAITING_VERIFICATION = "waiting_verification"
    WAITING_RECONCILIATION = "waiting_reconciliation"
    FAILED = "failed"


class GaojixingCollectionRun(TimestampMixin):
    """One immutable question package being collected for one workflow Run."""

    __tablename__ = "gaojixing_collection_runs"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", name="uq_gaojixing_collection_workflow_run"),
        CheckConstraint(
            "status IN ('queued', 'running', 'waiting_verification', "
            "'waiting_reconciliation', 'reviewing', 'succeeded', 'blocked', "
            "'failed', 'cancelled')",
            name="ck_gaojixing_collection_runs_status",
        ),
    )

    workflow_run_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    question_batch_ref: Mapped[str] = mapped_column(Text, nullable=False)
    question_bank_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default=GaojixingCollectionRunStatus.QUEUED.value
    )
    current_question_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    waiting_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    waiting_artifact_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_fencing_token: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class GaojixingQuestionCheckpoint(TimestampMixin):
    """Crash-safe progress for one exact question in an immutable package."""

    __tablename__ = "gaojixing_question_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "collection_run_id",
            "question_id",
            name="uq_gaojixing_checkpoint_question",
        ),
        UniqueConstraint(
            "collection_run_id",
            "position",
            name="uq_gaojixing_checkpoint_position",
        ),
        CheckConstraint("phase IN ('phase1', 'phase2')", name="ck_gaojixing_checkpoint_phase"),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'capturing', 'passed', "
            "'waiting_verification', 'waiting_reconciliation', 'failed')",
            name="ck_gaojixing_checkpoint_status",
        ),
    )

    collection_run_id: Mapped[str] = mapped_column(
        ForeignKey("gaojixing_collection_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[str] = mapped_column(String(16), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default=GaojixingQuestionStatus.PENDING.value
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chat_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversation_cleanup_pending: Mapped[bool] = mapped_column(
        nullable=False, default=False
    )
    artifact_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    failure: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class GaojixingRuntimeLease(TimestampMixin):
    """Singleton global browser-side-effect lease with a fencing token."""

    __tablename__ = "gaojixing_runtime_leases"

    owner: Mapped[str | None] = mapped_column(String(36), nullable=True)
    collection_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


GAOJIXING_GLOBAL_LEASE_ID = "gaojixing-doubao-live"


__all__ = [
    "GAOJIXING_GLOBAL_LEASE_ID",
    "GaojixingCollectionRun",
    "GaojixingCollectionRunStatus",
    "GaojixingQuestionCheckpoint",
    "GaojixingQuestionStatus",
    "GaojixingRuntimeLease",
]
