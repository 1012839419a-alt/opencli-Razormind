"""add OpenCLI-owned image studio domain

Revision ID: h5i6j7k8l9m0
Revises: g4h5i6j7k8l9
"""

import sqlalchemy as sa
from alembic import context, op

revision = "h5i6j7k8l9m0"
down_revision = "g4h5i6j7k8l9"
branch_labels = None
depends_on = None

_STUDIO_TABLES = {
    "studio_workspaces",
    "studio_projects",
    "studio_workflows",
    "studio_workflow_validation_runs",
}


def _timestamps() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    if (
        not context.is_offline_mode()
        and not _STUDIO_TABLES.issubset(sa.inspect(op.get_bind()).get_table_names())
    ):
        return

    op.add_column(
        "studio_workflow_validation_runs",
        sa.Column("resolved_graph", sa.JSON(), nullable=True),
    )
    op.create_table(
        "canvas_documents",
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("workflow_id", sa.String(36), nullable=False),
        sa.Column("node_id", sa.String(255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(100), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["studio_workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["studio_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"], ["studio_workflows.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "project_id",
            "workflow_id",
            "node_id",
            name="uq_canvas_document_workflow_node",
        ),
    )
    op.create_index("ix_canvas_documents_workspace_id", "canvas_documents", ["workspace_id"])
    op.create_index("ix_canvas_documents_project_id", "canvas_documents", ["project_id"])
    op.create_index("ix_canvas_documents_workflow_id", "canvas_documents", ["workflow_id"])

    op.create_table(
        "media_assets",
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("width > 0", name="ck_media_assets_width_positive"),
        sa.CheckConstraint("height > 0", name="ck_media_assets_height_positive"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["studio_workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["studio_projects.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "workspace_id", "project_id", "sha256", name="uq_media_asset_project_sha256"
        ),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_media_assets_workspace_id", "media_assets", ["workspace_id"])
    op.create_index("ix_media_assets_project_id", "media_assets", ["project_id"])

    op.create_table(
        "canvas_snapshots",
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("workflow_id", sa.String(36), nullable=False),
        sa.Column("node_id", sa.String(255), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("document_revision", sa.Integer(), nullable=False),
        sa.Column("canvas_document", sa.JSON(), nullable=False),
        sa.Column("executable_graph", sa.JSON(), nullable=False),
        sa.Column("model_fingerprint", sa.String(255), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("lora_revisions", sa.JSON(), nullable=False),
        sa.Column("asset_ids", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(100), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["studio_workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["studio_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"], ["studio_workflows.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["canvas_documents.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_canvas_snapshots_workspace_id", "canvas_snapshots", ["workspace_id"])
    op.create_index("ix_canvas_snapshots_project_id", "canvas_snapshots", ["project_id"])
    op.create_index("ix_canvas_snapshots_workflow_id", "canvas_snapshots", ["workflow_id"])
    op.create_index("ix_canvas_snapshots_node_id", "canvas_snapshots", ["node_id"])
    op.create_index("ix_canvas_snapshots_document_id", "canvas_snapshots", ["document_id"])

    op.create_table(
        "image_generation_jobs",
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("workflow_id", sa.String(36), nullable=False),
        sa.Column("node_id", sa.String(255), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("invoke_batch_id", sa.String(255), nullable=True),
        sa.Column("invoke_queue_item_id", sa.String(255), nullable=True),
        sa.Column("invoke_session_id", sa.String(255), nullable=True),
        sa.Column("output_asset_ids", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('queued', 'submitted', 'running', 'ingesting', 'succeeded', "
            "'blocked', 'failed', 'cancelled', 'timed_out')",
            name="ck_image_generation_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["studio_workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["studio_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"], ["studio_workflows.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["canvas_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_image_generation_job_idempotency"
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "run_id",
            "node_id",
            "attempt",
            name="uq_image_generation_job_run_node_attempt",
        ),
    )
    op.create_index(
        "ix_image_generation_jobs_workspace_id", "image_generation_jobs", ["workspace_id"]
    )
    op.create_index(
        "ix_image_generation_jobs_project_id", "image_generation_jobs", ["project_id"]
    )
    op.create_index(
        "ix_image_generation_jobs_workflow_id", "image_generation_jobs", ["workflow_id"]
    )
    op.create_index("ix_image_generation_jobs_node_id", "image_generation_jobs", ["node_id"])
    op.create_index("ix_image_generation_jobs_run_id", "image_generation_jobs", ["run_id"])
    op.create_index(
        "ix_image_generation_jobs_snapshot_id", "image_generation_jobs", ["snapshot_id"]
    )


def downgrade() -> None:
    if (
        not context.is_offline_mode()
        and not _STUDIO_TABLES.issubset(sa.inspect(op.get_bind()).get_table_names())
    ):
        return

    op.drop_table("image_generation_jobs")
    op.drop_table("canvas_snapshots")
    op.drop_table("media_assets")
    op.drop_table("canvas_documents")
    op.drop_column("studio_workflow_validation_runs", "resolved_graph")
