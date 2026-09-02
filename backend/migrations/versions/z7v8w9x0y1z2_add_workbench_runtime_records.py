"""add durable coding workbench records

Revision ID: z7v8w9x0y1z2
Revises: z6u7v8w9x0y1, k8l9m0n1o2p3
Create Date: 2026-08-29
"""

import sqlalchemy as sa
from alembic import op

revision = "z7v8w9x0y1z2"
down_revision = ("z6u7v8w9x0y1", "k8l9m0n1o2p3")
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "workbench_repositories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("repository_path", sa.Text(), nullable=False),
        sa.Column("base_ref", sa.String(length=255), nullable=False),
        sa.Column("worktree_root", sa.Text(), nullable=False),
        sa.Column("execution_node_url", sa.String(length=512), nullable=False),
        sa.Column("shared_filesystem_id", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "name"),
    )
    op.create_index(
        "ix_workbench_repositories_workspace_id", "workbench_repositories", ["workspace_id"]
    )

    op.create_table(
        "workbench_threads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('active', 'closed')", name="ck_workbench_threads_status"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["repository_id"], ["workbench_repositories.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workbench_threads_workspace_id", "workbench_threads", ["workspace_id"])
    op.create_index("ix_workbench_threads_repository_id", "workbench_threads", ["repository_id"])

    op.create_table(
        "workbench_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("operations_agent_id", sa.String(length=36), nullable=False),
        sa.Column("published_version", sa.Integer(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("runtime_type", sa.String(length=64), nullable=False),
        sa.Column("workflow", sa.String(length=255), nullable=False),
        sa.Column("base_sha", sa.String(length=64), nullable=False),
        sa.Column("worktree_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("next_event_sequence", sa.Integer(), nullable=False),
        sa.Column("cancelled_by_user_id", sa.String(length=36), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'proposed', 'applied', 'failed', 'cancelled')",
            name="ck_workbench_turns_status",
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["workbench_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["operations_agent_id"], ["operations_agent_identities.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "sequence"),
        sa.UniqueConstraint("thread_id", "request_id"),
    )
    op.create_index("ix_workbench_turns_thread_id", "workbench_turns", ["thread_id"])
    op.create_index("ix_workbench_turns_workspace_id", "workbench_turns", ["workspace_id"])
    op.create_index(
        "ix_workbench_turns_operations_agent_id", "workbench_turns", ["operations_agent_id"]
    )

    op.create_table(
        "workbench_turn_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "event_type IN ('started', 'text', 'tool_call', 'tool_result', 'state', "
            "'proposal', 'done', 'error', 'cancelled')",
            name="ck_workbench_turn_events_type",
        ),
        sa.ForeignKeyConstraint(["turn_id"], ["workbench_turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id", "sequence"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_workbench_turn_events_turn_id", "workbench_turn_events", ["turn_id"])

    op.create_table(
        "workbench_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("base_sha", sa.String(length=64), nullable=False),
        sa.Column("checkpoint_sha", sa.String(length=64), nullable=False),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("modified_files", sa.JSON(), nullable=False),
        sa.Column("tests", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confirmed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('pending_confirmation', 'applied', 'failed', 'cancelled')",
            name="ck_workbench_proposals_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["repository_id"], ["workbench_repositories.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["turn_id"], ["workbench_turns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id"),
    )
    op.create_index("ix_workbench_proposals_workspace_id", "workbench_proposals", ["workspace_id"])
    op.create_index(
        "ix_workbench_proposals_repository_id", "workbench_proposals", ["repository_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_workbench_proposals_repository_id", table_name="workbench_proposals")
    op.drop_index("ix_workbench_proposals_workspace_id", table_name="workbench_proposals")
    op.drop_table("workbench_proposals")
    op.drop_index("ix_workbench_turn_events_turn_id", table_name="workbench_turn_events")
    op.drop_table("workbench_turn_events")
    op.drop_index("ix_workbench_turns_operations_agent_id", table_name="workbench_turns")
    op.drop_index("ix_workbench_turns_workspace_id", table_name="workbench_turns")
    op.drop_index("ix_workbench_turns_thread_id", table_name="workbench_turns")
    op.drop_table("workbench_turns")
    op.drop_index("ix_workbench_threads_repository_id", table_name="workbench_threads")
    op.drop_index("ix_workbench_threads_workspace_id", table_name="workbench_threads")
    op.drop_table("workbench_threads")
    op.drop_index("ix_workbench_repositories_workspace_id", table_name="workbench_repositories")
    op.drop_table("workbench_repositories")
