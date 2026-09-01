"""add durable global agent conversations

Revision ID: s0t1u2v3w4x5
Revises: k8l9m0n1o2p3, 1901f6da7138
"""

import sqlalchemy as sa
from alembic import op

revision = "s0t1u2v3w4x5"
down_revision = ("k8l9m0n1o2p3", "1901f6da7138")
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("context_binding", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('active', 'closed')", name="ck_agent_conversations_status"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_agent_conversations_workspace_id", "agent_conversations", ["workspace_id"])
    op.create_index(
        "ix_agent_conversations_workspace_updated",
        "agent_conversations",
        ["workspace_id", "updated_at"],
    )
    op.create_table(
        "agent_conversation_turns",
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("user_content", sa.Text(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("context_binding", sa.JSON(), nullable=False),
        sa.Column("tool_trace", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'proposal', 'failed')",
            name="ck_agent_conversation_turns_status",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["agent_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
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
    op.create_index(
        "ix_agent_conversation_turns_conversation_sequence",
        "agent_conversation_turns",
        ["conversation_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_conversation_turns_conversation_sequence", table_name="agent_conversation_turns"
    )
    op.drop_index("ix_agent_conversation_turns_workspace_id", table_name="agent_conversation_turns")
    op.drop_index(
        "ix_agent_conversation_turns_conversation_id", table_name="agent_conversation_turns"
    )
    op.drop_table("agent_conversation_turns")
    op.drop_index("ix_agent_conversations_workspace_updated", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_workspace_id", table_name="agent_conversations")
    op.drop_table("agent_conversations")
