"""add opencli default runtime bundle v2

Revision ID: m0n1o2p3q4r5
Revises: l9m0n1o2p3q4
Create Date: 2026-08-29
"""

import json
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "m0n1o2p3q4r5"
down_revision = "l9m0n1o2p3q4"
branch_labels = None
depends_on = None

V1_BUNDLE_ID = "f4bce7f9-1df8-4e18-b671-37aa03230e93"
V2_BUNDLE_ID = "b5b4d7d1-a2f7-4e53-92cf-9d85f9fca3bc"


V2_BUNDLE_MANIFEST = {
    "name": "opencli-default",
    "version": "2",
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
        {
            "kind": "extension",
            "id": "violentmonkey",
            "version": "2.48.0",
            "path": "extensions/violentmonkey",
            "required": True,
            "capabilities": [],
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


def _table_exists(table_name: str) -> bool:
    context = op.get_context()
    if context.as_sql:
        return True
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    bundles = sa.table(
        "browser_runtime_bundles",
        sa.column("id", sa.String), sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)), sa.column("name", sa.String),
        sa.column("version", sa.String), sa.column("manifest", sa.JSON),
        sa.column("trust_level", sa.String), sa.column("source", sa.String),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        bundles,
        [
            {
                "id": V2_BUNDLE_ID,
                "created_at": now,
                "updated_at": now,
                "name": "opencli-default",
                "version": "2",
                "manifest": op.inline_literal(json.dumps(V2_BUNDLE_MANIFEST)),
                "trust_level": "system",
                "source": "image",
            }
        ],
        multiinsert=False,
    )
    if _table_exists("browser_instances"):
        op.execute(
            sa.text(
                "UPDATE browser_instances SET runtime_bundle_id = :v2 "
                "WHERE runtime_bundle_id = :v1"
            ).bindparams(v2=V2_BUNDLE_ID, v1=V1_BUNDLE_ID)
        )
        if _table_exists("browser_runtime_deployments"):
            op.execute(
                sa.text(
                    "UPDATE browser_runtime_deployments "
                    "SET state = 'RESTART_REQUIRED' "
                    "WHERE browser_instance_id IN ("
                    "SELECT id FROM browser_instances WHERE runtime_bundle_id = :v2"
                    ")"
                ).bindparams(v2=V2_BUNDLE_ID)
            )


def downgrade() -> None:
    if _table_exists("browser_instances"):
        op.execute(
            sa.text(
                "UPDATE browser_instances SET runtime_bundle_id = :v1 "
                "WHERE runtime_bundle_id = :v2"
            ).bindparams(v1=V1_BUNDLE_ID, v2=V2_BUNDLE_ID)
        )
        if _table_exists("browser_runtime_deployments"):
            op.execute(
                sa.text(
                    "UPDATE browser_runtime_deployments "
                    "SET state = 'RESTART_REQUIRED' "
                    "WHERE browser_instance_id IN ("
                    "SELECT id FROM browser_instances WHERE runtime_bundle_id = :v1"
                    ")"
                ).bindparams(v1=V1_BUNDLE_ID)
            )
    op.execute(
        sa.text("DELETE FROM browser_runtime_bundles WHERE id = :v2").bindparams(
            v2=V2_BUNDLE_ID
        )
    )
