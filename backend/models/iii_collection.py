"""Durable Admin-owned III collection command and lifecycle ledger."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import TimestampMixin


class IIICollectionCommandV1(TimestampMixin):
    """One immutable, scoped request to collect through the III OpenCLI function."""

    __tablename__ = "iii_collection_commands"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_iii_collection_command_run_key"),
        Index("ix_iii_collection_commands_scope", "workspace_id", "project_id", "workflow_id"),
    )

    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("studio_workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("studio_projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("studio_workflows.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    studio_workflow_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("studio_workflow_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_binding_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_binding_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_binding_revision_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    odp_source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    collector_function_id: Mapped[str] = mapped_column(String(100), nullable=False)
    collector_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)


class IIICollectionAttemptV1(TimestampMixin):
    """One Admin-allocated attempt under an immutable collection command."""

    __tablename__ = "iii_collection_attempts"
    __table_args__ = (
        UniqueConstraint("command_id", "attempt_number", name="uq_iii_collection_attempt_number"),
    )

    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    command_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iii_collection_commands.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    trace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)


class IIICollectionOutboundV1(TimestampMixin):
    """Mutable delivery bookkeeping, deliberately separate from command intent."""

    __tablename__ = "iii_collection_outbox"
    __table_args__ = (Index("ix_iii_collection_outbox_delivery", "state", "available_at"),)

    attempt_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iii_collection_attempts.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    dispatch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class IIICollectionLifecycleObservationV1(TimestampMixin):
    """Replay-safe bridge observation; details must remain redacted summaries."""

    __tablename__ = "iii_collection_lifecycle_observations"
    __table_args__ = (
        UniqueConstraint(
            "command_id",
            "attempt_id",
            "sequence",
            name="uq_iii_collection_lifecycle_replay",
        ),
        Index("ix_iii_collection_lifecycle_attempt", "attempt_id", "sequence"),
    )
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")

    command_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iii_collection_commands.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attempt_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iii_collection_attempts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class IIICollectionExpectedKeyReportV1(TimestampMixin):
    """Immutable collector completion boundary; never a persistence assertion."""

    __tablename__ = "iii_collection_expected_key_reports"
    __table_args__ = (
        UniqueConstraint("report_id", name="uq_iii_collection_expected_key_report_id"),
        UniqueConstraint(
            "command_id",
            "attempt_id",
            "report_sequence",
            name="uq_iii_collection_expected_key_report_replay",
        ),
        Index("ix_iii_collection_expected_key_report_attempt", "attempt_id", "report_sequence"),
    )

    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    report_id: Mapped[str] = mapped_column(String(128), nullable=False)
    command_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("iii_collection_commands.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("iii_collection_attempts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    report_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    key_set_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    zero_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_keys: Mapped[list] = mapped_column(JSON, nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class IIICollectionIngressReceiptV1(TimestampMixin):
    """Signed odp-ingest validation/enqueue observation; deliberately nonterminal."""

    __tablename__ = "iii_collection_ingress_receipts"
    __table_args__ = (
        UniqueConstraint("receipt_id", name="uq_iii_collection_ingress_receipt_id"),
        UniqueConstraint(
            "producer_id",
            "idempotency_key",
            name="uq_iii_collection_ingress_receipt_replay",
        ),
        Index("ix_iii_collection_ingress_receipt_attempt", "attempt_id", "issued_at"),
    )

    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    receipt_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    producer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    producer_key_id: Mapped[str] = mapped_column(String(255), nullable=False)
    command_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("iii_collection_commands.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("iii_collection_attempts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_key_set_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    outcomes: Mapped[list] = mapped_column(JSON, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    receipt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
