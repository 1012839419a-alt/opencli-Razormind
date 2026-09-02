"""add collection lineage envelopes to records and notification logs

Revision ID: ab2c3d4e5f6a
Revises: aa1b2c3d4e5f, f5a6b7c8d9e0, w3c4d5e6f7g8
"""

import sqlalchemy as sa
from alembic import context, op

revision = "ab2c3d4e5f6a"
down_revision = ("aa1b2c3d4e5f", "f5a6b7c8d9e0", "w3c4d5e6f7g8")
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        for table in ("collected_records", "notification_logs"):
            op.add_column(table, sa.Column("lineage", sa.JSON(), nullable=True))
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("collected_records", "notification_logs"):
        if table not in inspector.get_table_names():
            continue
        columns = {item["name"] for item in inspector.get_columns(table)}
        if "lineage" not in columns:
            op.add_column(table, sa.Column("lineage", sa.JSON(), nullable=True))


def downgrade() -> None:
    if context.is_offline_mode():
        for table in ("notification_logs", "collected_records"):
            op.drop_column(table, "lineage")
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("notification_logs", "collected_records"):
        if table not in inspector.get_table_names():
            continue
        columns = {item["name"] for item in inspector.get_columns(table)}
        if "lineage" in columns:
            op.drop_column(table, "lineage")
