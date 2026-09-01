"""Add workspace-scoped plugin lifecycle state.

Revision ID: l0m1n2o3p4q5
Revises: k8l9m0n1o2p3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "l0m1n2o3p4q5"
down_revision: str | None = "k8l9m0n1o2p3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Some databases were stamped past the original repair migration while
    # their plugin table was still missing. Recreate the legacy shape here so
    # the lifecycle migration can safely bring those databases to the head.
    if not context.is_offline_mode() and not sa.inspect(op.get_bind()).has_table(
        "plugin_installations"
    ):
        op.create_table(
            "plugin_installations",
            sa.Column("provider_key", sa.String(length=257), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("author", sa.String(length=128), nullable=False),
            sa.Column("version", sa.String(length=64), nullable=False),
            sa.Column("source_kind", sa.String(length=32), nullable=False),
            sa.Column("source_digest", sa.String(length=64), nullable=False),
            sa.Column("manifest_spec_version", sa.String(length=32), nullable=False),
            sa.Column("signature_state", sa.String(length=32), nullable=False),
            sa.Column("manifest_json", sa.JSON(), nullable=False),
            sa.Column("capabilities_json", sa.JSON(), nullable=False),
            sa.Column("permissions_json", sa.JSON(), nullable=False),
            sa.Column("runtime_status", sa.String(length=32), nullable=False),
            sa.Column("blockers_json", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "provider_key",
                "version",
                "source_digest",
                name="uq_plugin_installations_provider_version_digest",
            ),
        )
        op.create_index(
            "ix_plugin_installations_provider_key",
            "plugin_installations",
            ["provider_key"],
            unique=False,
        )

    with op.batch_alter_table("plugin_installations") as batch_op:
        batch_op.add_column(sa.Column("workspace_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column(
                "granted_permissions_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.drop_constraint(
            "uq_plugin_installations_provider_version_digest", type_="unique"
        )
        batch_op.create_unique_constraint(
            "uq_plugin_installations_workspace_provider_version_digest",
            ["workspace_id", "provider_key", "version", "source_digest"],
        )
        batch_op.create_index(
            "ix_plugin_installations_workspace_id", ["workspace_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_plugin_installations_workspace_id_workspaces",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.alter_column("enabled", server_default=None)
        batch_op.alter_column("granted_permissions_json", server_default=None)

    # Preserve legacy global installations; new workspace installs stay opt-in.
    op.execute(sa.text("UPDATE plugin_installations SET enabled = true"))
    op.create_index(
        "uq_plugin_installations_global_provider_version_digest",
        "plugin_installations",
        ["provider_key", "version", "source_digest"],
        unique=True,
        sqlite_where=sa.text("workspace_id IS NULL"),
        postgresql_where=sa.text("workspace_id IS NULL"),
    )


def downgrade() -> None:
    workspace_count = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM plugin_installations "
            "WHERE workspace_id IS NOT NULL"
        )
    ).scalar_one()
    if workspace_count:
        raise RuntimeError(
            "Cannot downgrade workspace plugin lifecycle while workspace installations exist."
        )
    op.drop_index(
        "uq_plugin_installations_global_provider_version_digest",
        table_name="plugin_installations",
    )
    with op.batch_alter_table("plugin_installations") as batch_op:
        batch_op.drop_constraint(
            "fk_plugin_installations_workspace_id_workspaces", type_="foreignkey"
        )
        batch_op.drop_index("ix_plugin_installations_workspace_id")
        batch_op.drop_constraint(
            "uq_plugin_installations_workspace_provider_version_digest", type_="unique"
        )
        batch_op.create_unique_constraint(
            "uq_plugin_installations_provider_version_digest",
            ["provider_key", "version", "source_digest"],
        )
        batch_op.drop_column("granted_permissions_json")
        batch_op.drop_column("enabled")
        batch_op.drop_column("workspace_id")
