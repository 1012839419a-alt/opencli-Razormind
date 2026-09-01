"""Durable ownership and task-lease records for managed browser runtimes."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import TimestampMixin


class BrowserSpaceStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    CLOSED = "closed"
    ERROR = "error"


class BrowserSpaceTaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BrowserSpaceEventKind(StrEnum):
    QUEUED = "queued"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    CLOSED = "closed"


class BrowserSpace(TimestampMixin):
    """One Workspace-owned reservation for one managed BrowserInstance."""

    __tablename__ = "browser_spaces"
    __table_args__ = (
        CheckConstraint(
            "owner_type IN ('operator', 'runtime_agent')", name="ck_browser_spaces_owner"
        ),
        CheckConstraint(
            "status IN ('idle', 'running', 'closed', 'error')", name="ck_browser_spaces_status"
        ),
        # SQLite and PostgreSQL both support this partial index. Closed spaces deliberately
        # release the physical instance while preserving the audit record.
        Index(
            "uq_browser_spaces_active_instance",
            "browser_instance_id",
            unique=True,
            sqlite_where=text("status <> 'closed'"),
            postgresql_where=text("status <> 'closed'"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    browser_instance_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("browser_instances.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    binding_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("browser_bindings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BrowserSpaceStatus.IDLE.value
    )
    granted_capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class BrowserSpaceTask(TimestampMixin):
    """One idempotent, serialized capability invocation in a BrowserSpace."""

    __tablename__ = "browser_space_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_browser_space_tasks_status",
        ),
        Index(
            "uq_browser_space_tasks_active_space",
            "space_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index("uq_browser_space_tasks_operation_id", "operation_id", unique=True),
        Index("uq_browser_space_tasks_space_request", "space_id", "request_id", unique=True),
    )

    space_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("browser_spaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    capability: Mapped[str] = mapped_column(String(255), nullable=False)
    args: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BrowserSpaceTaskStatus.QUEUED.value
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BrowserSpaceEvent(TimestampMixin):
    """Append-only, per-Space ordered lifecycle event."""

    __tablename__ = "browser_space_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('queued', 'started', 'completed', 'failed', "
            "'cancel_requested', 'cancelled', 'closed')",
            name="ck_browser_space_events_kind",
        ),
        Index("uq_browser_space_events_sequence", "space_id", "sequence", unique=True),
    )

    space_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("browser_spaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # A close event belongs to the Space rather than a task, so this remains nullable.
    task_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("browser_space_tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
