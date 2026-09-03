from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.channels.base import FetchResult
from backend.schemas.workflow import (
    CollectorNodeParams,
    CompiledWorkflowNode,
    WorkflowProjectNode,
)
from backend.workflow import opencli_hda_tracer as tracer
from backend.workflow.runtime_registry import (
    COLLECTOR_BINDING_PREFIX,
    MERGE_BINDING_ID,
    SOURCE_FETCH_BINDING_ID,
    resolve_runtime_metadata,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_frontend_catalog_defaults_validate_at_backend_schema_boundary():
    completed = subprocess.run(
        [
            "node",
            "frontend/scripts/check-collector-l1-regressions.mjs",
            "--print-catalog-defaults",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    nodes = json.loads(completed.stdout.strip())

    assert len(nodes) == 4
    for payload in nodes:
        node = WorkflowProjectNode.model_validate(payload)
        CollectorNodeParams.model_validate(node.params)

    defaults_by_kind = {
        payload["ui"]["catalogId"].rsplit(".", 1)[-1]: payload["params"]["sources"]
        for payload in nodes
    }
    assert defaults_by_kind["web"][0]["fetchMode"] == "auto"
    assert defaults_by_kind["rss"][0]["itemLimit"] == 20
    assert "limit" not in defaults_by_kind["rss"][0]


def _collector_node(*sources: dict, execution: dict | None = None) -> CompiledWorkflowNode:
    return CompiledWorkflowNode(
        id="collector",
        kind="source",
        capability="fetch",
        params={},
        runtime={
            "binding": {
                "binding_id": SOURCE_FETCH_BINDING_ID,
                "input": {
                    "collectorType": "api",
                    "sources": list(sources),
                    "execution": execution or {},
                },
            }
        },
    )


@pytest.mark.asyncio
async def test_collector_fanout_retries_only_retryable_failures_and_keeps_partial_success(
    monkeypatch,
):
    calls: defaultdict[str, int] = defaultdict(int)

    async def collect_once(source, source_type):
        source_id = source["sourceId"]
        calls[source_id] += 1
        if source_id == "retry" and calls[source_id] == 1:
            raise TimeoutError("temporary timeout")
        if source_id == "permanent":
            raise ValueError("bad mapping")
        return [{"title": source_id}]

    monkeypatch.setattr(tracer, "_collect_source_once", collect_once)
    node = _collector_node(
        {"sourceId": "ok", "kind": "api", "url": "https://example.com"},
        {"sourceId": "retry", "kind": "api", "url": "https://example.com"},
        {"sourceId": "permanent", "kind": "api", "url": "https://example.com"},
        {"sourceId": "off", "kind": "api", "url": "https://example.com", "enabled": False},
        execution={"retry": {"maxAttempts": 3, "backoffMs": 0}},
    )

    items, results = await tracer._execute_collector_source_node(node)

    assert [item["sourceId"] for item in items] == ["ok", "retry"]
    assert [result["status"] for result in results] == [
        "completed",
        "completed",
        "failed",
        "skipped",
    ]
    assert results[1]["attempts"] == 2
    assert results[2]["attempts"] == 1
    assert results[2]["error"]["retryable"] is False
    assert results[3]["attempts"] == 0
    assert calls == {"ok": 1, "retry": 2, "permanent": 1}


@pytest.mark.asyncio
async def test_collector_item_keeps_missing_published_at_null_and_redacts_secrets(monkeypatch):
    async def collect_once(source, source_type):
        return [{"title": "fresh", "token": "must-not-leak", "nested": {"password": "x"}}]

    monkeypatch.setattr(tracer, "_collect_source_once", collect_once)
    items, results = await tracer._execute_collector_source_node(
        _collector_node(
            {
                "sourceId": "source-a",
                "kind": "api",
                "url": "https://example.com",
                "credentialRef": "credential://source-a",
            }
        )
    )

    assert results[0]["status"] == "completed"
    assert items[0]["publishedAt"] is None
    assert items[0]["fetchedAt"]
    assert "token" not in items[0]["data"]
    assert "password" not in items[0]["data"]["nested"]


@pytest.mark.asyncio
async def test_collector_all_enabled_sources_failed_returns_no_items(monkeypatch):
    async def collect_once(source, source_type):
        raise ValueError("invalid source")

    monkeypatch.setattr(tracer, "_collect_source_once", collect_once)
    items, results = await tracer._execute_collector_source_node(
        _collector_node(
            {"sourceId": "a", "kind": "api", "url": "https://example.com/a"},
            {"sourceId": "b", "kind": "api", "url": "https://example.com/b"},
        )
    )

    assert items == []
    assert [result["status"] for result in results] == ["failed", "failed"]


@pytest.mark.asyncio
async def test_four_collector_kinds_dispatch_to_registered_channels(monkeypatch):
    seen: list[tuple[str, dict]] = []

    class Channel:
        def __init__(self, name):
            self.name = name

        async def fetch(self, ctx):
            seen.append((self.name, ctx.config))
            return FetchResult(items=[{"title": self.name}])

    monkeypatch.setattr(
        "backend.channels.registry.get_channel",
        lambda name: Channel(name),
    )
    monkeypatch.setattr(
        "backend.workflow.opencli_adapter_nodes.resolve_opencli_adapter_node",
        lambda adapter_node_id: (
            SimpleNamespace(
                site="demo",
                command="list",
                access="read",
                args=[
                    SimpleNamespace(
                        name="limit",
                        type="int",
                        required=False,
                        choices=[],
                    )
                ],
            )
            if adapter_node_id == "opencli.adapter.demo.list"
            else None
        ),
    )
    sources = [
        {"sourceId": "w", "kind": "web", "url": "https://example.com", "extraction": {}},
        {"sourceId": "a", "kind": "api", "url": "https://example.com/api", "query": {}},
        {"sourceId": "r", "kind": "rss", "feedUrl": "https://example.com/feed", "itemLimit": 5},
        {
            "sourceId": "c",
            "kind": "cli",
            "adapterNodeId": "opencli.adapter.demo.list",
            "args": {"limit": 5},
        },
    ]

    for source in sources:
        await tracer._collect_source_once(source, source["kind"])

    assert [name for name, _ in seen] == ["web_scraper", "api", "rss", "opencli"]
    assert seen[1][1]["base_url"] == "https://example.com/api"
    assert seen[2][1]["max_entries"] == 5
    assert seen[3][1]["site"] == "demo"
    assert seen[3][1]["command"] == "list"
    assert seen[3][1]["args"] == {"limit": 5}


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        (
            {"query": "topic", "unknown": "--write-like-option"},
            "unknown_opencli_adapter_arguments",
        ),
        (
            {"query": "topic", "limit": "five"},
            "invalid_opencli_adapter_argument_type",
        ),
        (
            {"query": "topic", "format": "xml"},
            "invalid_opencli_adapter_argument_choice",
        ),
        ({}, "missing_opencli_adapter_arguments"),
    ],
)
def test_cli_collector_rejects_arguments_outside_registered_typed_schema(
    arguments,
    error,
):
    from backend.workflow.opencli_adapter_nodes import validate_opencli_adapter_arguments

    adapter = SimpleNamespace(
        args=[
            SimpleNamespace(
                name="limit",
                type="int",
                required=False,
                choices=[],
            ),
            SimpleNamespace(
                name="format",
                type="str",
                required=False,
                choices=["json", "csv"],
            ),
            SimpleNamespace(
                name="query",
                type="str",
                required=True,
                choices=[],
            ),
        ]
    )

    with pytest.raises(ValueError, match=error):
        validate_opencli_adapter_arguments(adapter, arguments)


@pytest.mark.parametrize("upstream_count", [1, 2, 5])
@pytest.mark.asyncio
async def test_variadic_merge_preserves_edge_order_items_source_results_and_lineage(
    upstream_count,
):
    dependency_ids = [f"source-{index}" for index in reversed(range(upstream_count))]
    node = CompiledWorkflowNode(
        id="merge",
        kind="flow",
        capability="merge",
        depends_on=dependency_ids,
        runtime={
            "binding": {
                "binding_id": MERGE_BINDING_ID,
                "input": {"strategy": "concat", "preserveLineage": True},
            }
        },
    )
    outputs = {
        source_id: [{"itemId": source_id, "lineage": {"sourceId": source_id}}]
        for source_id in reversed(dependency_ids)
    }
    source_results = {
        source_id: [{"sourceId": source_id, "status": "completed"}]
        for source_id in outputs
    }

    details, merged = await tracer._execute_native_node(
        node,
        outputs,
        source_results,
        "run",
        workflow_id="workflow",
        trace_id="trace",
    )

    assert [item["itemId"] for item in merged] == dependency_ids
    assert merged[0]["lineage"] == {"sourceId": dependency_ids[0]}
    assert [result["sourceId"] for result in details["sourceResults"]] == dependency_ids


@pytest.mark.asyncio
async def test_variadic_merge_requires_at_least_one_upstream():
    node = CompiledWorkflowNode(
        id="merge",
        kind="flow",
        capability="merge",
        runtime={"binding": {"binding_id": MERGE_BINDING_ID, "input": {}}},
    )
    with pytest.raises(ValueError, match="merge_input_required"):
        await tracer._execute_native_node(
            node,
            {},
            {},
            "run",
            workflow_id="workflow",
            trace_id="trace",
        )


def test_runtime_registry_binds_collector_without_adapter_and_filters_plaintext_credentials():
    node = WorkflowProjectNode.model_construct(
        id="collector",
        kind="source",
        capability="fetch",
        ui={"catalogId": "collection.source.api"},
        params={
            "version": 1,
            "execution": {"retry": {"maxAttempts": 2}},
            "sources": [
                {
                    "sourceId": "api-a",
                    "kind": "api",
                    "url": "https://example.com",
                    "credentialRef": "credential://api-a",
                    "token": "must-not-leak",
                }
            ],
        },
    )

    metadata = resolve_runtime_metadata(node, None)
    binding_input = metadata["binding"]["input"]

    assert metadata["binding"]["binding_id"] == f"{COLLECTOR_BINDING_PREFIX}api"
    assert binding_input["collectorType"] == "api"
    assert binding_input["sources"][0]["credentialRef"] == "credential://api-a"
    assert "token" not in binding_input["sources"][0]
