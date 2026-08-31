"""add stable first-party starter identity to automations"""

import sqlalchemy as sa
from alembic import op

revision = "aa1b2c3d4e5f"
down_revision = "k8l9m0n1o2p3"
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "automations" not in inspector.get_table_names():
        return
    columns = {item["name"] for item in inspector.get_columns("automations")}
    if "starter_key" not in columns:
        op.add_column("automations", sa.Column("starter_key", sa.String(64), nullable=True))
    # A unique index is portable to SQLite (where ALTER TABLE cannot add a
    # table-level unique constraint) and has the same uniqueness semantics.
    indexes = {item["name"] for item in inspector.get_indexes("automations")}
    if "uq_automations_workspace_starter_key" not in indexes:
        op.create_index(
            "uq_automations_workspace_starter_key",
            "automations",
            ["workspace_id", "starter_key"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "automations" not in inspector.get_table_names():
        return
    indexes = {item["name"] for item in inspector.get_indexes("automations")}
    if "uq_automations_workspace_starter_key" in indexes:
        op.drop_index("uq_automations_workspace_starter_key", table_name="automations")
    columns = {item["name"] for item in inspector.get_columns("automations")}
    if "starter_key" in columns:
        op.drop_column("automations", "starter_key")
