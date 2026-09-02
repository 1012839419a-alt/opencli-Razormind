"""add capability-selected universal agent runtime envelopes

Revision ID: cd4e5f6a7b8c
Revises: bc3d4e5f6a7b
"""

from copy import deepcopy

import sqlalchemy as sa
from alembic import op

revision = "cd4e5f6a7b8c"
down_revision = "bc3d4e5f6a7b"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _has_column(bind, table: str, column: str) -> bool:
    return column in {item["name"] for item in sa.inspect(bind).get_columns(table)}


def _migrate_configuration(configuration: dict) -> dict:
    migrated = deepcopy(configuration)
    contract = migrated.get("agent_contract")
    if isinstance(contract, dict) and contract.get("schema_version") == "agent.contract.v1":
        contract["schema_version"] = "agent.contract.v2"
        contract.setdefault("role", "operations_agent")
        contract.setdefault("required_capabilities", ["streaming"])
        contract.setdefault("tool_policy", {})
        contract.setdefault("budget", {})
        contract.setdefault("quality_gates", [])
        contract.setdefault("evidence_requirements", [])

    binding = migrated.get("runtime_binding")
    if isinstance(binding, dict) and binding.get("schema_version") == "agent.runtime-binding.v1":
        agent_url = binding.get("agent_url")
        runtime = binding.get("runtime")
        migrated["runtime_binding"] = {
            "schema_version": "agent.runtime-binding.v2",
            "workflow": binding.get("workflow") or "default",
            "preferred_agent_urls": [agent_url] if isinstance(agent_url, str) and agent_url else [],
            "preferred_runtimes": [runtime] if isinstance(runtime, str) and runtime else [],
            "model_binding": None,
            "config": binding.get("config") or {},
            "dispatch_timeout_seconds": binding.get("dispatch_timeout_seconds", 1800),
        }
    return migrated


def _downgrade_configuration(configuration: dict) -> dict:
    downgraded = deepcopy(configuration)
    contract = downgraded.get("agent_contract")
    if isinstance(contract, dict) and contract.get("schema_version") == "agent.contract.v2":
        downgraded["agent_contract"] = {
            "schema_version": "agent.contract.v1",
            "input_schema": contract.get("input_schema") or {},
            "output_schema": contract.get("output_schema") or {},
            "state_schema": contract.get("state_schema") or {},
        }

    binding = downgraded.get("runtime_binding")
    if isinstance(binding, dict) and binding.get("schema_version") == "agent.runtime-binding.v2":
        urls = binding.get("preferred_agent_urls") or []
        runtimes = binding.get("preferred_runtimes") or []
        runtime = (
            runtimes[0]
            if runtimes and runtimes[0] in {"miniflow", "pi", "codex"}
            else "miniflow"
        )
        downgraded["runtime_binding"] = {
            "schema_version": "agent.runtime-binding.v1",
            "agent_url": urls[0] if urls else "http://unbound.invalid",
            "runtime": runtime,
            "workflow": binding.get("workflow") or "default",
            "config": binding.get("config") or {},
            "dispatch_timeout_seconds": binding.get("dispatch_timeout_seconds", 1800),
        }
    return downgraded


def _rewrite_agent_configurations(bind, transform) -> None:
    for table_name in ("operations_agent_drafts", "published_operations_agent_versions"):
        if not _has_table(bind, table_name):
            continue
        table = sa.table(
            table_name,
            sa.column("id", sa.String()),
            sa.column("model_configuration", sa.JSON()),
        )
        rows = bind.execute(sa.select(table.c.id, table.c.model_configuration)).mappings()
        for row in rows:
            configuration = row["model_configuration"]
            if isinstance(configuration, dict):
                bind.execute(
                    table.update()
                    .where(table.c.id == row["id"])
                    .values(model_configuration=transform(configuration))
                )


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "edge_nodes") and not _has_column(
        bind, "edge_nodes", "runtime_capabilities"
    ):
        op.add_column(
            "edge_nodes",
            sa.Column("runtime_capabilities", sa.JSON(), nullable=True),
        )
    if _has_table(bind, "operations_agent_runs"):
        if not _has_column(bind, "operations_agent_runs", "execution_binding"):
            op.add_column(
                "operations_agent_runs",
                sa.Column("execution_binding", sa.JSON(), nullable=True),
            )
        if not _has_column(bind, "operations_agent_runs", "evidence_payload"):
            op.add_column(
                "operations_agent_runs",
                sa.Column("evidence_payload", sa.JSON(), nullable=True),
            )
    _rewrite_agent_configurations(bind, _migrate_configuration)


def downgrade() -> None:
    bind = op.get_bind()
    _rewrite_agent_configurations(bind, _downgrade_configuration)
    if _has_table(bind, "operations_agent_runs"):
        if _has_column(bind, "operations_agent_runs", "evidence_payload"):
            op.drop_column("operations_agent_runs", "evidence_payload")
        if _has_column(bind, "operations_agent_runs", "execution_binding"):
            op.drop_column("operations_agent_runs", "execution_binding")
    if _has_table(bind, "edge_nodes") and _has_column(bind, "edge_nodes", "runtime_capabilities"):
        op.drop_column("edge_nodes", "runtime_capabilities")
