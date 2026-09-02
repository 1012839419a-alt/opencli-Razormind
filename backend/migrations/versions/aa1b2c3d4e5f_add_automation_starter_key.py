"""add stable first-party starter identity to automations"""

import sqlalchemy as sa
from alembic import op

revision = "aa1b2c3d4e5f"
down_revision = "k8l9m0n1o2p3"
depends_on = None


def _table_exists(table_name: str) -> bool:
    context = op.get_context()
    if context.as_sql:
        return True
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _table_exists("automations"):
        return
    op.add_column("automations", sa.Column("starter_key", sa.String(64), nullable=True))
    # A unique index is portable to SQLite (where ALTER TABLE cannot add a
    # table-level unique constraint) and has the same uniqueness semantics.
    op.create_index(
        "uq_automations_workspace_starter_key",
        "automations",
        ["workspace_id", "starter_key"],
        unique=True,
    )


def downgrade() -> None:
    if not _table_exists("automations"):
        return
    op.drop_index("uq_automations_workspace_starter_key", table_name="automations")
    op.drop_column("automations", "starter_key")
