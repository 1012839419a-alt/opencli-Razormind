"""add Browser Space ownership and task lease records

Revision ID: l9m0n1o2p3q4
Revises: k8l9m0n1o2p3
Create Date: 2026-09-01
"""

import sqlalchemy as sa
from alembic import op

revision = "l9m0n1o2p3q4"
down_revision = "k8l9m0n1o2p3"
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
        "browser_spaces",
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("browser_instance_id", sa.String(36), nullable=False),
        sa.Column("binding_id", sa.String(36), nullable=True),
        sa.Column("owner_type", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("granted_capabilities", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "owner_type IN ('operator', 'runtime_agent')", name="ck_browser_spaces_owner"
        ),
        sa.CheckConstraint(
            "status IN ('idle', 'running', 'closed', 'error')", name="ck_browser_spaces_status"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["browser_instance_id"], ["browser_instances.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["binding_id"], ["browser_bindings.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_browser_spaces_workspace_id", "browser_spaces", ["workspace_id"])
    op.create_index(
        "ix_browser_spaces_browser_instance_id", "browser_spaces", ["browser_instance_id"]
    )
    op.create_index("ix_browser_spaces_binding_id", "browser_spaces", ["binding_id"])
    op.create_index(
        "uq_browser_spaces_active_instance",
        "browser_spaces",
        ["browser_instance_id"],
        unique=True,
        sqlite_where=sa.text("status <> 'closed'"),
        postgresql_where=sa.text("status <> 'closed'"),
    )
    op.create_table(
        "browser_space_tasks",
        sa.Column("space_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("operation_id", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(255), nullable=False),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_browser_space_tasks_status",
        ),
        sa.ForeignKeyConstraint(["space_id"], ["browser_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_browser_space_tasks_space_id", "browser_space_tasks", ["space_id"])
    op.create_index("ix_browser_space_tasks_workspace_id", "browser_space_tasks", ["workspace_id"])
    op.create_index(
        "uq_browser_space_tasks_operation_id", "browser_space_tasks", ["operation_id"], unique=True
    )
    op.create_index(
        "uq_browser_space_tasks_space_request",
        "browser_space_tasks",
        ["space_id", "request_id"],
        unique=True,
    )
    op.create_index(
        "uq_browser_space_tasks_active_space",
        "browser_space_tasks",
        ["space_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running')"),
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "browser_space_events",
        sa.Column("space_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "kind IN ('queued', 'started', 'completed', 'failed', "
            "'cancel_requested', 'cancelled', 'closed')",
            name="ck_browser_space_events_kind",
        ),
        sa.ForeignKeyConstraint(["space_id"], ["browser_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["browser_space_tasks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_browser_space_events_space_id", "browser_space_events", ["space_id"])
    op.create_index("ix_browser_space_events_task_id", "browser_space_events", ["task_id"])
    op.create_index(
        "uq_browser_space_events_sequence",
        "browser_space_events",
        ["space_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_browser_space_events_sequence", table_name="browser_space_events")
    op.drop_index("ix_browser_space_events_task_id", table_name="browser_space_events")
    op.drop_index("ix_browser_space_events_space_id", table_name="browser_space_events")
    op.drop_table("browser_space_events")
    op.drop_index("uq_browser_space_tasks_active_space", table_name="browser_space_tasks")
    op.drop_index("uq_browser_space_tasks_space_request", table_name="browser_space_tasks")
    op.drop_index("uq_browser_space_tasks_operation_id", table_name="browser_space_tasks")
    op.drop_index("ix_browser_space_tasks_workspace_id", table_name="browser_space_tasks")
    op.drop_index("ix_browser_space_tasks_space_id", table_name="browser_space_tasks")
    op.drop_table("browser_space_tasks")
    op.drop_index("uq_browser_spaces_active_instance", table_name="browser_spaces")
    op.drop_index("ix_browser_spaces_binding_id", table_name="browser_spaces")
    op.drop_index("ix_browser_spaces_browser_instance_id", table_name="browser_spaces")
    op.drop_index("ix_browser_spaces_workspace_id", table_name="browser_spaces")
    op.drop_table("browser_spaces")
