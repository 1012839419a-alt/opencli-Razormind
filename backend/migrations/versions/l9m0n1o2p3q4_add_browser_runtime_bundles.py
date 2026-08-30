"""add browser runtime bundles

Revision ID: l9m0n1o2p3q4
Revises: k8l9m0n1o2p3
Create Date: 2026-08-29
"""

import json
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

DEFAULT_BUNDLE_ID = "f4bce7f9-1df8-4e18-b671-37aa03230e93"
DEFAULT_BUNDLE_MANIFEST = {
    "name": "opencli-default",
    "version": "1",
    "components": [
        {
            "kind": "extension",
            "id": "opencli-browser-bridge",
            "version": "0.1.0",
            "path": "extensions/opencli-browser-bridge",
            "required": True,
            "capabilities": [],
        },
        {
            "kind": "extension",
            "id": "opencli-script-host",
            "version": "1.2.0",
            "path": "extensions/opencli-script-host",
            "required": True,
            "capabilities": ["page.metadata"],
        },
    ],
    "capabilities": [
        {
            "name": "page.metadata",
            "component_id": "opencli-script-host",
            "action": "page.metadata",
            "runtime": "script-host",
            "args_schema": {"type": "object", "additionalProperties": False},
            "allowed_hosts": [],
            "risk": "low",
            "required_gate": None,
            "config": {"pack": "page-basics"},
        }
    ],
    "act_pack_ids": [],
}

revision = "l9m0n1o2p3q4"
down_revision = "k8l9m0n1o2p3"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    context = op.get_context()
    if context.as_sql:
        return True
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    op.create_table(
        "browser_runtime_bundles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("trust_level", sa.String(length=30), nullable=False, server_default="trusted"),
        sa.Column("source", sa.String(length=255), nullable=False, server_default="local"),
        sa.UniqueConstraint("name", "version", name="uq_browser_runtime_bundle_version"),
    )
    bundle_table = sa.table(
        "browser_runtime_bundles",
        sa.column("id", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("name", sa.String),
        sa.column("version", sa.String),
        sa.column("manifest", sa.JSON),
        sa.column("trust_level", sa.String),
        sa.column("source", sa.String),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        bundle_table,
        [
            {
                "id": DEFAULT_BUNDLE_ID,
                "created_at": now,
                "updated_at": now,
                "name": "opencli-default",
                "version": "1",
                "manifest": op.inline_literal(json.dumps(DEFAULT_BUNDLE_MANIFEST)),
                "trust_level": "system",
                "source": "image",
            }
        ],
        multiinsert=False,
    )
    if not _table_exists("browser_instances"):
        return
    with op.batch_alter_table("browser_instances") as batch:
        batch.add_column(
            sa.Column("profile_name", sa.String(length=100), nullable=False, server_default="")
        )
        batch.add_column(sa.Column("runtime_bundle_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column(
                "resource_class", sa.String(length=100), nullable=False, server_default="standard"
            )
        )
        batch.add_column(
            sa.Column("startup_pages", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch.add_column(
            sa.Column("network_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch.create_foreign_key(
            "fk_browser_instances_runtime_bundle",
            "browser_runtime_bundles",
            ["runtime_bundle_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_browser_instances_runtime_bundle_id", ["runtime_bundle_id"])
    # Existing slots predate profiles and runtime reporting. Seed one profile
    # per endpoint, but leave runtime_bundle_id NULL so they retain legacy
    # admission semantics until an operator explicitly assigns a bundle.
    op.execute("UPDATE browser_instances SET profile_name = endpoint WHERE profile_name = ''")
    with op.batch_alter_table("browser_instances") as batch:
        batch.create_unique_constraint("uq_browser_instances_profile_name", ["profile_name"])

    op.create_table(
        "browser_runtime_deployments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("browser_instance_id", sa.String(length=36), nullable=False),
        sa.Column("loaded_bundle_name", sa.String(length=100), nullable=True),
        sa.Column("loaded_bundle_version", sa.String(length=100), nullable=True),
        sa.Column("loaded_components", sa.JSON(), nullable=False),
        sa.Column("self_check", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="DEGRADED"),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["browser_instance_id"], ["browser_instances.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("browser_instance_id", name="uq_browser_runtime_deployment_slot"),
    )
    op.create_index(
        "ix_browser_runtime_deployments_browser_instance_id",
        "browser_runtime_deployments",
        ["browser_instance_id"],
    )
    op.create_table(
        "browser_capability_invocations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("browser_instance_id", sa.String(length=36), nullable=False),
        sa.Column("capability", sa.String(length=255), nullable=False),
        sa.Column("desired_bundle_name", sa.String(length=100), nullable=True),
        sa.Column("desired_bundle_version", sa.String(length=100), nullable=True),
        sa.Column("loaded_bundle_version", sa.String(length=100), nullable=True),
        sa.Column("component_versions", sa.JSON(), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("page_before", sa.JSON(), nullable=True),
        sa.Column("page_after", sa.JSON(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("risk", sa.String(length=20), nullable=False),
        sa.Column("gate", sa.String(length=100), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["browser_instance_id"], ["browser_instances.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_browser_capability_invocations_browser_instance_id",
        "browser_capability_invocations",
        ["browser_instance_id"],
    )


def downgrade() -> None:
    if _table_exists("browser_capability_invocations"):
        op.drop_index(
            "ix_browser_capability_invocations_browser_instance_id",
            table_name="browser_capability_invocations",
        )
        op.drop_table("browser_capability_invocations")
    if _table_exists("browser_runtime_deployments"):
        op.drop_index(
            "ix_browser_runtime_deployments_browser_instance_id",
            table_name="browser_runtime_deployments",
        )
        op.drop_table("browser_runtime_deployments")
    if _table_exists("browser_instances"):
        with op.batch_alter_table("browser_instances") as batch:
            batch.drop_index("ix_browser_instances_runtime_bundle_id")
            batch.drop_constraint("fk_browser_instances_runtime_bundle", type_="foreignkey")
            batch.drop_constraint("uq_browser_instances_profile_name", type_="unique")
            batch.drop_column("network_policy")
            batch.drop_column("startup_pages")
            batch.drop_column("resource_class")
            batch.drop_column("runtime_bundle_id")
            batch.drop_column("profile_name")
    op.drop_table("browser_runtime_bundles")
