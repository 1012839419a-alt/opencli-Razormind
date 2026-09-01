"""add workspace-scoped Browser Space ownership and task leases

Revision ID: r8s9t0u1v2w3
Revises: l1m2n3o4p5q6

The active-resource indexes intentionally use partial uniqueness so closed
spaces/tasks do not hold reservations forever. Integration owns merging this
revision with any sibling migration heads.
"""

import sqlalchemy as sa
from alembic import op

revision = "r8s9t0u1v2w3"
down_revision = "l1m2n3o4p5q6"
branch_labels = None
depends_on = None


_ACTIVE_SPACES = sa.text("status IN ('idle', 'running', 'error')")
_ACTIVE_TASKS = sa.text("status IN ('queued', 'running')")


def upgrade() -> None:
    op.create_table(
        "browser_spaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("browser_instance_id", sa.String(length=36), nullable=False),
        sa.Column("binding_id", sa.String(length=36), nullable=True),
        sa.Column("owner_type", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="idle"),
        sa.Column("granted_capabilities", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "owner_type IN ('operator', 'runtime_agent')",
            name="ck_browser_spaces_owner_type",
        ),
        sa.CheckConstraint(
            "status IN ('idle', 'running', 'closed', 'error')",
            name="ck_browser_spaces_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["browser_instance_id"], ["browser_instances.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["binding_id"], ["browser_bindings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
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
        sqlite_where=_ACTIVE_SPACES,
        postgresql_where=_ACTIVE_SPACES,
    )

    op.create_table(
        "browser_space_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("space_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("operation_id", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=255), nullable=False),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_browser_space_tasks_status",
        ),
        sa.ForeignKeyConstraint(["space_id"], ["browser_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id", name="uq_browser_space_tasks_operation_id"),
    )
    op.create_index("ix_browser_space_tasks_space_id", "browser_space_tasks", ["space_id"])
    op.create_index("ix_browser_space_tasks_workspace_id", "browser_space_tasks", ["workspace_id"])
    op.create_index(
        "uq_browser_space_tasks_request",
        "browser_space_tasks",
        ["space_id", "request_id"],
        unique=True,
    )
    op.create_index(
        "uq_browser_space_tasks_active_space",
        "browser_space_tasks",
        ["space_id"],
        unique=True,
        sqlite_where=_ACTIVE_TASKS,
        postgresql_where=_ACTIVE_TASKS,
    )

    op.create_table(
        "browser_space_event_counters",
        sa.Column("space_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["space_id"], ["browser_spaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("space_id"),
    )


    op.create_table(
        "browser_space_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("space_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('queued', 'started', 'completed', 'failed', 'cancel_requested', 'cancelled')",
            name="ck_browser_space_events_kind",
        ),
        sa.ForeignKeyConstraint(["space_id"], ["browser_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["browser_space_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
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
    op.drop_table("browser_space_event_counters")
    op.drop_index("uq_browser_space_tasks_active_space", table_name="browser_space_tasks")
    op.drop_index("uq_browser_space_tasks_request", table_name="browser_space_tasks")
    op.drop_index("ix_browser_space_tasks_workspace_id", table_name="browser_space_tasks")
    op.drop_index("ix_browser_space_tasks_space_id", table_name="browser_space_tasks")
    op.drop_table("browser_space_tasks")
    op.drop_index("uq_browser_spaces_active_instance", table_name="browser_spaces")
    op.drop_index("ix_browser_spaces_binding_id", table_name="browser_spaces")
    op.drop_index("ix_browser_spaces_browser_instance_id", table_name="browser_spaces")
    op.drop_index("ix_browser_spaces_workspace_id", table_name="browser_spaces")
    op.drop_table("browser_spaces")
