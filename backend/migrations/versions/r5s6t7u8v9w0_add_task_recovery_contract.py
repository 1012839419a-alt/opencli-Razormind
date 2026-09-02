"""add governed task recovery contract

Revision ID: r5s6t7u8v9w0
Revises: q4r5s6t7u8v9
Create Date: 2026-09-02
"""

from alembic import context, op
import sqlalchemy as sa


revision = "r5s6t7u8v9w0"
down_revision = "q4r5s6t7u8v9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and not sa.inspect(op.get_bind()).has_table("collection_tasks"):
        return
    with op.batch_alter_table("collection_tasks") as batch:
        batch.add_column(sa.Column("retry_of_task_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("recovery_mode", sa.String(32), nullable=True))
        batch.add_column(sa.Column("recovery_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("initiating_actor", sa.String(255), nullable=True))
        batch.add_column(sa.Column("recovery_idempotency_key", sa.String(255), nullable=True))
        batch.create_foreign_key(
            "fk_collection_tasks_retry_of_task_id",
            "collection_tasks",
            ["retry_of_task_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint(
            "uq_collection_tasks_recovery_idempotency_key",
            ["recovery_idempotency_key"],
        )
    op.create_index("ix_collection_tasks_retry_of_task_id", "collection_tasks", ["retry_of_task_id"])


def downgrade() -> None:
    if not context.is_offline_mode() and not sa.inspect(op.get_bind()).has_table("collection_tasks"):
        return
    op.drop_index("ix_collection_tasks_retry_of_task_id", table_name="collection_tasks")
    with op.batch_alter_table("collection_tasks") as batch:
        batch.drop_constraint("uq_collection_tasks_recovery_idempotency_key", type_="unique")
        batch.drop_constraint("fk_collection_tasks_retry_of_task_id", type_="foreignkey")
        batch.drop_column("recovery_idempotency_key")
        batch.drop_column("initiating_actor")
        batch.drop_column("recovery_reason")
        batch.drop_column("recovery_mode")
        batch.drop_column("retry_of_task_id")
