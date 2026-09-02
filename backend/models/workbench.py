"""Durable, workspace-scoped coding workbench records."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import TimestampMixin


class WorkbenchRepository(TimestampMixin):
    """Server-managed repository/ref/worktree mapping; never browser supplied."""

    __tablename__ = "workbench_repositories"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_path: Mapped[str] = mapped_column(Text, nullable=False)
    base_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    worktree_root: Mapped[str] = mapped_column(Text, nullable=False)
    execution_node_url: Mapped[str] = mapped_column(String(512), nullable=False)
    shared_filesystem_id: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WorkbenchThread(TimestampMixin):
    """Operator-owned conversation, intentionally distinct from a runtime identity."""

    __tablename__ = "workbench_threads"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'closed')", name="ck_workbench_threads_status"),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("workbench_repositories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    turns: Mapped[list["WorkbenchTurn"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="WorkbenchTurn.sequence"
    )


class WorkbenchTurn(TimestampMixin):
    """One requirement submitted by an operator and pinned to a published runtime."""

    __tablename__ = "workbench_turns"
    __table_args__ = (
        UniqueConstraint("thread_id", "sequence"),
        UniqueConstraint("thread_id", "request_id"),
        CheckConstraint(
            "status IN ('queued', 'running', 'proposed', 'applied', 'failed', 'cancelled')",
            name="ck_workbench_turns_status",
        ),
    )

    thread_id: Mapped[str] = mapped_column(
        ForeignKey("workbench_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    operations_agent_id: Mapped[str] = mapped_column(
        ForeignKey("operations_agent_identities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    published_version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow: Mapped[str] = mapped_column(String(255), nullable=False)
    base_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    worktree_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cancelled_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    thread: Mapped[WorkbenchThread] = relationship(back_populates="turns")
    events: Mapped[list["WorkbenchTurnEvent"]] = relationship(
        back_populates="turn", cascade="all, delete-orphan", order_by="WorkbenchTurnEvent.sequence"
    )
    proposal: Mapped["WorkbenchProposal | None"] = relationship(
        back_populates="turn", cascade="all, delete-orphan", uselist=False
    )


class WorkbenchTurnEvent(TimestampMixin):
    """Append-only normalized event transcript for one Workbench turn."""

    __tablename__ = "workbench_turn_events"
    __table_args__ = (
        UniqueConstraint("turn_id", "sequence"),
        UniqueConstraint("event_id"),
        CheckConstraint(
            "event_type IN ('started', 'text', 'tool_call', 'tool_result', 'state', "
            "'proposal', 'done', 'error', 'cancelled')",
            name="ck_workbench_turn_events_type",
        ),
    )

    turn_id: Mapped[str] = mapped_column(
        ForeignKey("workbench_turns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    turn: Mapped[WorkbenchTurn] = relationship(back_populates="events")


class WorkbenchProposal(TimestampMixin):
    """Inspect-only controller checkpoint that can be applied only after confirmation."""

    __tablename__ = "workbench_proposals"
    __table_args__ = (
        UniqueConstraint("turn_id"),
        CheckConstraint(
            "status IN ('pending_confirmation', 'applied', 'failed', 'cancelled')",
            name="ck_workbench_proposals_status",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("workbench_repositories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    turn_id: Mapped[str] = mapped_column(
        ForeignKey("workbench_turns.id", ondelete="CASCADE"), nullable=False
    )
    base_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    diff: Mapped[str] = mapped_column(Text, nullable=False)
    modified_files: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    tests: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_confirmation")
    confirmed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    turn: Mapped[WorkbenchTurn] = relationship(back_populates="proposal")
