"""add persistent Global Agent conversations

Revision ID: l1m2n3o4p5q6
Revises: q4r5s6t7u8v9
Create Date: 2026-09-01
"""

import sqlalchemy as sa
from alembic import op

revision = "l1m2n3o4p5q6"
down_revision = "q4r5s6t7u8v9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("context_binding", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'closed')", name="ck_agent_conversations_status"),
        sa.CheckConstraint("revision >= 0", name="ck_agent_conversations_revision_nonnegative"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_conversations_workspace_id", "agent_conversations", ["workspace_id"])
    op.create_index(
        "ix_agent_conversations_created_by_user_id",
        "agent_conversations",
        ["created_by_user_id"],
    )

    op.create_table(
        "agent_conversation_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("user_content", sa.Text(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("context_binding", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("tool_trace", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'proposal', 'failed')",
            name="ck_agent_conversation_turns_status",
        ),
        sa.CheckConstraint("sequence > 0", name="ck_agent_conversation_turns_sequence_positive"),
        sa.CheckConstraint(
            "length(request_id) BETWEEN 1 AND 64",
            name="ck_agent_conversation_turn_request_length",
        ),
        sa.CheckConstraint(
            "length(user_content) <= 20000", name="ck_agent_conversation_turns_content_length"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["agent_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id", "sequence", name="uq_agent_conversation_turn_sequence"
        ),
        sa.UniqueConstraint(
            "conversation_id", "request_id", name="uq_agent_conversation_turn_request"
        ),
    )
    op.create_index(
        "ix_agent_conversation_turns_conversation_id",
        "agent_conversation_turns",
        ["conversation_id"],
    )
    op.create_index(
        "ix_agent_conversation_turns_workspace_id", "agent_conversation_turns", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_table("agent_conversation_turns")
    op.drop_index("ix_agent_conversations_created_by_user_id", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_workspace_id", table_name="agent_conversations")
    op.drop_table("agent_conversations")
