"""add Feishu delivery connections and idempotent attempts

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
"""

import sqlalchemy as sa
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_connections",
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("app_id", sa.String(255), nullable=False),
        sa.Column("app_secret", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "delivery_attempts",
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("delivery_connections.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("app_token", sa.String(255), nullable=False),
        sa.Column("table_id", sa.String(255), nullable=False),
        sa.Column("record_id", sa.String(36), nullable=False),
        sa.Column("workflow_run_id", sa.String(36)),
        sa.Column("evidence_digest", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("remote_record_id", sa.String(255)),
        sa.Column("error_code", sa.String(96)),
        sa.Column("field_map", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "connection_id",
            "app_token",
            "table_id",
            "record_id",
            name="uq_delivery_attempt_target_record",
        ),
    )
    op.create_index(
        "ix_delivery_attempts_connection_id", "delivery_attempts", ["connection_id"]
    )
    op.create_index("ix_delivery_attempts_record_id", "delivery_attempts", ["record_id"])
    op.create_index(
        "ix_delivery_attempts_workflow_run_id", "delivery_attempts", ["workflow_run_id"]
    )


def downgrade() -> None:
    op.drop_table("delivery_attempts")
    op.drop_table("delivery_connections")
