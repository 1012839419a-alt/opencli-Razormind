"""repair collected record identity schema drift

Revision ID: i6j7k8l9m0n1
Revises: h5i6j7k8l9m0
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import context, op

revision = "i6j7k8l9m0n1"
down_revision = "h5i6j7k8l9m0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("collected_records"):
        return

    columns = {column["name"] for column in inspector.get_columns("collected_records")}
    indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("collected_records")
    }

    if "identity_key" not in columns:
        with op.batch_alter_table("collected_records") as batch:
            batch.add_column(sa.Column("identity_key", sa.String(length=512), nullable=True))

    index_name = "ix_collected_records_source_identity"
    expected_columns = ("source_id", "identity_key")
    if index_name in indexes and indexes[index_name] != expected_columns:
        raise RuntimeError(
            f"{index_name} has columns {indexes[index_name]}, expected {expected_columns}"
        )
    if index_name not in indexes:
        op.create_index(
            index_name,
            "collected_records",
            list(expected_columns),
            unique=False,
        )


def downgrade() -> None:
    # This schema belongs to u0a1b2c3d4e5; this repair revision never owns its removal.
    pass
