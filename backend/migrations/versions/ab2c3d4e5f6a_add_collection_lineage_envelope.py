"""add collection lineage envelopes to records and notification logs

Revision ID: ab2c3d4e5f6a
Revises: aa1b2c3d4e5f, f5a6b7c8d9e0, w3c4d5e6f7g8
"""

import sqlalchemy as sa
from alembic import op

revision = "ab2c3d4e5f6a"
down_revision = ("aa1b2c3d4e5f", "f5a6b7c8d9e0", "w3c4d5e6f7g8")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collected_records",
        sa.Column("lineage", sa.JSON(), nullable=True),
    )
    op.add_column(
        "notification_logs",
        sa.Column("lineage", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_logs", "lineage")
    op.drop_column("collected_records", "lineage")
