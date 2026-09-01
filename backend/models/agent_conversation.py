"""Durable, workspace-scoped Global Agent conversation records."""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import TimestampMixin


class AgentConversation(TimestampMixin):
    __tablename__ = "agent_conversations"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'closed')", name="ck_agent_conversations_status"),
        Index("ix_agent_conversations_workspace_updated", "workspace_id", "updated_at"),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    context_binding: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AgentConversationTurn(TimestampMixin):
    __tablename__ = "agent_conversation_turns"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_agent_conversation_turn_sequence"),
        UniqueConstraint(
            "conversation_id", "request_id", name="uq_agent_conversation_turn_request"
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'proposal', 'failed')",
            name="ck_agent_conversation_turns_status",
        ),
        Index("ix_agent_conversation_turns_conversation_sequence", "conversation_id", "sequence"),
    )

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_content: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_binding: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tool_trace: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
