"""add durable Gaojixing collection runtime

Revision ID: b9c0d1e2f3a5
Revises: a8b9c0d1e2f3
"""

import sqlalchemy as sa
from alembic import op

revision = "b9c0d1e2f3a5"
down_revision = "a8b9c0d1e2f3"
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
        "gaojixing_collection_runs",
        sa.Column("workflow_run_id", sa.String(36), nullable=False),
        sa.Column("node_id", sa.String(255), nullable=False),
        sa.Column("question_batch_ref", sa.Text(), nullable=False),
        sa.Column("question_bank_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("current_question_id", sa.String(16), nullable=True),
        sa.Column("waiting_kind", sa.String(64), nullable=True),
        sa.Column("waiting_artifact_ref", sa.Text(), nullable=True),
        sa.Column("failure", sa.JSON(), nullable=True),
        sa.Column("lease_owner", sa.String(36), nullable=True),
        sa.Column("lease_fencing_token", sa.Integer(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "workflow_run_id", name="uq_gaojixing_collection_workflow_run"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'waiting_verification', "
            "'waiting_reconciliation', 'reviewing', 'succeeded', 'blocked', "
            "'failed', 'cancelled')",
            name="ck_gaojixing_collection_runs_status",
        ),
    )
    op.create_index(
        "ix_gaojixing_collection_runs_workflow_run_id",
        "gaojixing_collection_runs",
        ["workflow_run_id"],
    )
    op.create_index(
        "ix_gaojixing_collection_runs_lease_expires_at",
        "gaojixing_collection_runs",
        ["lease_expires_at"],
    )
    op.create_table(
        "gaojixing_question_checkpoints",
        sa.Column("collection_run_id", sa.String(36), nullable=False),
        sa.Column("question_id", sa.String(16), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("chat_url", sa.Text(), nullable=True),
        sa.Column("raw_digest", sa.String(64), nullable=True),
        sa.Column("artifact_refs", sa.JSON(), nullable=False),
        sa.Column("failure", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["collection_run_id"], ["gaojixing_collection_runs.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "collection_run_id",
            "question_id",
            name="uq_gaojixing_checkpoint_question",
        ),
        sa.UniqueConstraint(
            "collection_run_id",
            "position",
            name="uq_gaojixing_checkpoint_position",
        ),
        sa.CheckConstraint(
            "phase IN ('phase1', 'phase2')", name="ck_gaojixing_checkpoint_phase"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'capturing', 'passed', "
            "'waiting_verification', 'waiting_reconciliation', 'failed')",
            name="ck_gaojixing_checkpoint_status",
        ),
    )
    op.create_index(
        "ix_gaojixing_question_checkpoints_collection_run_id",
        "gaojixing_question_checkpoints",
        ["collection_run_id"],
    )
    op.create_table(
        "gaojixing_runtime_leases",
        sa.Column("owner", sa.String(36), nullable=True),
        sa.Column("collection_run_id", sa.String(36), nullable=True),
        sa.Column("fencing_token", sa.Integer(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index(
        "ix_gaojixing_runtime_leases_expires_at",
        "gaojixing_runtime_leases",
        ["expires_at"],
    )
    lease_id = "gaojixing-doubao-live"
    op.execute(
        sa.text(
            "INSERT INTO gaojixing_runtime_leases "
            "(id, owner, collection_run_id, fencing_token, heartbeat_at, expires_at, "
            "created_at, updated_at) VALUES "
            "(:id, NULL, NULL, 0, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ).bindparams(id=lease_id)
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gaojixing_runtime_leases_expires_at",
        table_name="gaojixing_runtime_leases",
    )
    op.drop_table("gaojixing_runtime_leases")
    op.drop_index(
        "ix_gaojixing_question_checkpoints_collection_run_id",
        table_name="gaojixing_question_checkpoints",
    )
    op.drop_table("gaojixing_question_checkpoints")
    op.drop_index(
        "ix_gaojixing_collection_runs_lease_expires_at",
        table_name="gaojixing_collection_runs",
    )
    op.drop_index(
        "ix_gaojixing_collection_runs_workflow_run_id",
        table_name="gaojixing_collection_runs",
    )
    op.drop_table("gaojixing_collection_runs")
