"""Acceptance tests for native DataFlow preparation and cleaning operators."""

import json
from copy import deepcopy

import pytest
from sqlalchemy import select

from backend.models.record import CollectedRecord

_OPERATOR_CASES = [
    pytest.param(
        "core.generate.instruction-pairs",
        "generate",
        [{"title": "Guide", "content": "Use the guide."}],
        {"instructionTemplate": "Answer from {title}"},
        1,
        id="core-generate-instruction-pairs",
    ),
    pytest.param(
        "core.filter.quality",
        "filter",
        [{"title": "Guide", "content": "Useful content"}],
        {"minLength": 1},
        1,
        id="core-filter-quality",
    ),
    pytest.param(
        "core.evaluate.quality",
        "evaluate",
        [{"title": "Guide", "content": "Useful content"}],
        {"minLength": 1},
        1,
        id="core-evaluate-quality",
    ),
    pytest.param(
        "core.refine.text",
        "refine",
        [{"title": "Guide", "content": "  MIXED   Case  "}],
        {"fields": ["content"], "lowercase": True},
        1,
        id="core-refine-text",
    ),
    pytest.param(
        "text.clean",
        "refine",
        [{"title": "Guide", "content": "<p>Clean   me</p>"}],
        {"fields": ["content"], "operations": ["htmlTags", "whitespace"]},
        1,
        id="text-clean",
    ),
    pytest.param(
        "text.rule-filter",
        "filter",
        [{"title": "Guide", "content": "Keep this text"}],
        {"fields": ["content"], "minWords": 2},
        1,
        id="text-rule-filter",
    ),
    pytest.param(
        "text.deduplicate",
        "filter",
        [
            {"title": "Guide", "content": "Same text"},
            {"title": "Guide", "content": "Same text"},
        ],
        {"fields": ["content"], "mode": "exact"},
        1,
        id="text-deduplicate",
    ),
    pytest.param(
        "text.statistics",
        "evaluate",
        [{"title": "Guide", "content": "Count these words"}],
        {"fields": ["content"], "outputField": "statistics"},
        1,
        id="text-statistics",
    ),
    pytest.param(
        "data.project",
        "refine",
        [{"title": "Guide", "content": "Projected text"}],
        {"rename": {"title": "heading"}},
        1,
        id="data-project",
    ),
    pytest.param(
        "data.chunk",
        "generate",
        [{"title": "Guide", "content": "abcdef"}],
        {"chunkSize": 3, "overlap": 1},
        3,
        id="data-chunk",
    ),
    pytest.param(
        "data.qa-extract",
        "generate",
        [
            {
                "title": "Guide",
                "content": "Grounded context",
                "qaPairs": [{"question": "What?", "answer": "This."}],
            }
        ],
        {},
        1,
        id="data-qa-extract",
    ),
    pytest.param(
        "data.training-format",
        "refine",
        [{"title": "Question", "content": "Answer"}],
        {
            "format": "alpaca",
            "instructionField": "title",
            "inputField": "content",
            "outputField": "content",
        },
        1,
        id="data-training-format",
    ),
]

_EXPECTED_OPERATOR_MANIFEST = {
    "intelligence.data.generate": [
        {
            "id": "core.generate.instruction-pairs",
            "operatorId": "core.generate.instruction-pairs",
            "kind": "generate",
            "label": "Instruction pairs",
            "packId": "builtin.core-data",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": [
                "instructionField",
                "responseField",
                "instructionTemplate",
            ],
        },
        {
            "id": "data.chunk",
            "operatorId": "data.chunk",
            "kind": "generate",
            "label": "Data chunk",
            "packId": "builtin.dataset-preparation",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": ["field", "chunkSize", "overlap"],
        },
        {
            "id": "data.qa-extract",
            "operatorId": "data.qa-extract",
            "kind": "generate",
            "label": "QA extract",
            "packId": "builtin.dataset-preparation",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": ["pairsField", "contextField"],
        },
    ],
    "intelligence.data.filter": [
        {
            "id": "core.filter.quality",
            "operatorId": "core.filter.quality",
            "kind": "filter",
            "label": "Quality filter",
            "packId": "builtin.core-data",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": [
                "fields",
                "requiredFields",
                "textField",
                "minChars",
                "maxChars",
                "minLength",
                "maxLength",
                "minQuality",
                "blocklist",
            ],
        },
        {
            "id": "text.deduplicate",
            "operatorId": "text.deduplicate",
            "kind": "filter",
            "label": "Text deduplicate",
            "packId": "builtin.text-cleaning",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": ["fields", "mode", "maxHammingDistance"],
        },
        {
            "id": "text.deduplicate",
            "operatorId": "text.deduplicate",
            "kind": "filter",
            "label": "Text deduplicate",
            "packId": "builtin.text-cleaning",
            "packVersion": "1.1.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": [
                "fields",
                "hashFunction",
                "mode",
                "nGram",
                "diffSize",
                "outputKey",
            ],
        },
        {
            "id": "text.rule-filter",
            "operatorId": "text.rule-filter",
            "kind": "filter",
            "label": "Text rule filter",
            "packId": "builtin.text-cleaning",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": [
                "fields",
                "minChars",
                "maxChars",
                "minWords",
                "maxWords",
                "minSentences",
                "maxSymbolRatio",
                "minUniqueWordRatio",
                "blocklist",
            ],
        },
        {
            "id": "text.rule-filter",
            "operatorId": "text.rule-filter",
            "kind": "filter",
            "label": "Text rule filter",
            "packId": "builtin.text-cleaning",
            "packVersion": "1.1.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": ["fields", "rules"],
        },
    ],
    "intelligence.data.evaluate": [
        {
            "id": "core.evaluate.quality",
            "operatorId": "core.evaluate.quality",
            "kind": "evaluate",
            "label": "Quality evaluation",
            "packId": "builtin.core-data",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": ["fields", "minLength", "maxLength"],
        },
        {
            "id": "text.statistics",
            "operatorId": "text.statistics",
            "kind": "evaluate",
            "label": "Text statistics",
            "packId": "builtin.text-cleaning",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": ["fields", "outputField"],
        },
    ],
    "intelligence.data.refine": [
        {
            "id": "core.refine.text",
            "operatorId": "core.refine.text",
            "kind": "refine",
            "label": "Text refine",
            "packId": "builtin.core-data",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": [
                "fields",
                "lowercase",
                "unicodeForm",
                "redactEmail",
                "redactPhone",
            ],
        },
        {
            "id": "data.project",
            "operatorId": "data.project",
            "kind": "refine",
            "label": "Data project",
            "packId": "builtin.dataset-preparation",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": ["select", "rename", "coalesce", "casts"],
        },
        {
            "id": "data.training-format",
            "operatorId": "data.training-format",
            "kind": "refine",
            "label": "Training format",
            "packId": "builtin.dataset-preparation",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": [
                "format",
                "instructionField",
                "inputField",
                "outputField",
                "resultField",
            ],
        },
        {
            "id": "text.clean",
            "operatorId": "text.clean",
            "kind": "refine",
            "label": "Text clean",
            "packId": "builtin.text-cleaning",
            "packVersion": "1.0.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": ["fields", "operations", "replacement"],
        },
        {
            "id": "text.clean",
            "operatorId": "text.clean",
            "kind": "refine",
            "label": "Text clean",
            "packId": "builtin.text-cleaning",
            "packVersion": "1.1.0",
            "status": "runnable",
            "readiness": "ready",
            "configKeys": ["fields", "operations", "htmlEntities"],
        },
    ],
}


def _operator_node(node_id: str, operator_id: str, kind: str, **config) -> dict:
    return {
        "id": node_id,
        "kind": "agent",
        "capability": "normalize",
        "params": {"operatorId": operator_id, **config},
        "ui": {"catalogId": f"intelligence.data.{kind}"},
    }


def _single_operator_project(
    operator_id: str,
    kind: str,
    fixture_items: list[dict],
    config: dict,
) -> dict:
    params = {"operatorId": operator_id, **config}
    if operator_id == "core.filter.quality":
        # Nested config is canonical and must override the legacy flat value.
        params = {
            "operatorId": operator_id,
            "minLength": 999,
            "config": config,
        }
    operator_node = _operator_node("operator", operator_id, kind)
    operator_node["params"] = params
    return {
        "id": f"wf-{operator_id}",
        "name": f"Operator {operator_id}",
        "profile": "intelligence",
        "version": 1,
        "nodes": [
            {
                "id": "fixture-source",
                "kind": "source",
                "capability": "fetch",
                "adapter": "fixture-adapter",
                "params": {"fixtureItems": fixture_items},
            },
            {
                "id": "normalize",
                "kind": "agent",
                "capability": "normalize",
                "params": {},
                "ui": {"catalogId": "intelligence.processing.normalize"},
            },
            operator_node,
        ],
        "edges": [
            {
                "id": "e-source-normalize",
                "source": "fixture-source",
                "target": "normalize",
            },
            {
                "id": "e-normalize-operator",
                "source": "normalize",
                "target": "operator",
                "sourcePort": "out",
                "targetPort": "in",
            },
        ],
        "adapters": [
            {
                "id": "fixture-adapter",
                "type": "source",
                "provider": "fixture",
                "mode": "fixture",
                "config": {},
            }
        ],
        "agentPermissions": {},
    }


def _dataflow_pipeline_project() -> dict:
    nodes = [
        {
            "id": "fixture-source",
            "kind": "source",
            "capability": "fetch",
            "adapter": "fixture-adapter",
            "params": {
                "fixtureItems": [
                    {
                        "title": "DataFlow guide",
                        "url": "https://example.com/dataflow",
                        "content": "<p>Prepare   grounded QA data 😊</p>",
                        "QA_pairs": [
                            {
                                "question": "What does the guide prepare?",
                                "answer": "Grounded QA data.",
                                "context": "Prepare grounded QA data.",
                                "source": "https://example.com/dataflow",
                            }
                        ],
                    },
                    {
                        "title": "DataFlow guide",
                        "url": "https://example.com/dataflow",
                        "content": "<p>Prepare   grounded QA data 😊</p>",
                        "QA_pairs": [
                            {
                                "question": "What does the guide prepare?",
                                "answer": "Grounded QA data.",
                                "context": "Prepare grounded QA data.",
                                "source": "https://example.com/dataflow",
                            }
                        ],
                    },
                    {
                        "title": "Reject",
                        "url": "https://example.com/reject",
                        "content": "DROP_THIS noisy payload",
                        "QA_pairs": [
                            {
                                "question": "Should this survive?",
                                "answer": "No.",
                                "context": "DROP_THIS noisy payload",
                                "source": "https://example.com/reject",
                            }
                        ],
                    },
                ]
            },
        },
        {
            "id": "normalize",
            "kind": "agent",
            "capability": "normalize",
            "params": {"preserveSourceRefs": True},
            "ui": {"catalogId": "intelligence.processing.normalize"},
        },
        _operator_node(
            "project",
            "data.project",
            "refine",
        ),
        _operator_node(
            "chunk",
            "data.chunk",
            "generate",
            chunkSize=200,
            overlap=20,
        ),
        _operator_node(
            "clean",
            "text.clean",
            "refine",
            fields=["content"],
            operations=["htmlEntities", "htmlTags", "emoji", "whitespace"],
        ),
        _operator_node(
            "rule-filter",
            "text.rule-filter",
            "filter",
            fields=["content"],
            blocklist=["DROP_THIS"],
        ),
        _operator_node(
            "deduplicate",
            "text.deduplicate",
            "filter",
            fields=["content"],
            mode="exact",
        ),
        _operator_node(
            "qa-extract",
            "data.qa-extract",
            "generate",
            pairsField="extra_QA_pairs",
        ),
        _operator_node(
            "training-format",
            "data.training-format",
            "refine",
            format="alpaca",
        ),
        {
            "id": "accept",
            "kind": "control",
            "capability": "accept",
            "params": {
                "mode": "automatic_with_review",
                "schema": "record.v1",
                "dedupe": "required",
                "lineageRequired": True,
                "minQuality": 0,
            },
            "ui": {"catalogId": "intelligence.control.record-acceptance"},
        },
        {
            "id": "record-sink",
            "kind": "sink",
            "capability": "store",
            "params": {
                "target": "records",
                "writeMode": "append",
                "preserveLineage": True,
            },
            "ui": {"catalogId": "intelligence.sink.records"},
        },
    ]
    ordered_ids = [node["id"] for node in nodes]
    edges = [
        {
            "id": f"e-{source}-{target}",
            "source": source,
            "target": target,
            "sourcePort": (
                "records"
                if source == "accept"
                else "out"
            ),
            "targetPort": (
                "candidates"
                if target == "accept"
                else "records"
                if target == "record-sink"
                else "in"
            ),
        }
        for source, target in zip(ordered_ids, ordered_ids[1:])
    ]
    return {
        "id": "wf-dataflow-acceptance",
        "name": "DataFlow acceptance pipeline",
        "profile": "intelligence",
        "version": 1,
        # Deliberately reverse declarations: execution must follow graph topology.
        "nodes": list(reversed(nodes)),
        "edges": edges,
        "settings": {
            "timezone": "Asia/Shanghai",
            "deterministicSimulation": True,
            "maxItemsPerRun": 100,
        },
        "adapters": [
            {
                "id": "fixture-adapter",
                "type": "source",
                "provider": "fixture",
                "mode": "fixture",
                "config": {},
            }
        ],
        "agentPermissions": {"canWriteInbox": True},
    }


def _minimal_operator_project(
    *,
    catalog_kind: str = "generate",
    operator_id: str | None = "data.chunk",
) -> dict:
    node = _operator_node(
        "operator",
        operator_id or "",
        catalog_kind,
    )
    if operator_id is None:
        node["params"].pop("operatorId")
    return {
        "id": "wf-invalid-data-operator",
        "name": "Invalid data operator",
        "profile": "intelligence",
        "version": 1,
        "nodes": [node],
        "edges": [],
        "adapters": [],
        "agentPermissions": {},
    }


@pytest.mark.asyncio
async def test_dataflow_pipeline_runs_topologically_with_lineage_metrics_and_sink(
    client,
    db_session,
):
    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": _dataflow_pipeline_project(),
            "runId": "run-dataflow-acceptance",
            "traceId": "trace-dataflow-acceptance",
        },
    )

    assert response.status_code == 202
    run = response.json()["data"]
    assert run["valid"] is True
    assert run["status"] == "completed"

    events = (
        await client.get("/api/v1/workflows/runs/run-dataflow-acceptance/events")
    ).json()["data"]
    partials = {
        event["nodeId"]: event["details"]
        for event in events
        if event["eventType"] == "partial"
    }
    operator_ids = [
        "project",
        "chunk",
        "clean",
        "rule-filter",
        "deduplicate",
        "qa-extract",
        "training-format",
    ]
    started_order = [
        event["nodeId"]
        for event in events
        if event["eventType"] == "started" and event["nodeId"] in operator_ids
    ]
    assert started_order == operator_ids

    for node_id in operator_ids:
        details = partials[node_id]
        assert details["inputPort"] == "recordCandidate[]"
        assert details["outputPort"] == "recordCandidate[]"
        assert details["metrics"]["inputItemCount"] == details["inputItemCount"]
        assert details["metrics"]["outputItemCount"] == details["outputItemCount"]
        assert details["lineage"]["nodeId"] == node_id

    assert partials["rule-filter"]["rejectedCount"] == 1
    assert len(partials["rule-filter"]["rejectedCandidateIds"]) == 1
    assert partials["rule-filter"]["rejectedCandidateIdsTruncated"] is False
    assert partials["deduplicate"]["rejectedCount"] == 1
    assert len(partials["deduplicate"]["rejectedCandidateIds"]) == 1
    assert partials["deduplicate"]["rejectedCandidateIdsTruncated"] is False
    assert partials["qa-extract"]["outputItemCount"] == 1
    assert partials["training-format"]["outputItemCount"] == 1

    records = (await db_session.execute(select(CollectedRecord))).scalars().all()
    assert len(records) == 1
    record = records[0]
    assert record.normalized_data["trainingData"] == {
        "instruction": "What does the guide prepare?",
        "input": "Prepare grounded QA data",
        "output": "Grounded QA data.",
    }
    assert record.normalized_data["context"] == "Prepare grounded QA data"
    assert {"url": "https://example.com/dataflow"} in record.normalized_data[
        "sourceRefs"
    ]
    lineage = record.raw_data["_workflowLineage"]
    assert [entry["nodeId"] for entry in lineage] == [
        "fixture-source",
        "normalize",
        *operator_ids,
        "accept",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operator_id", "kind", "fixture_items", "config", "expected_output_count"),
    _OPERATOR_CASES,
)
async def test_each_dataflow_operator_compiles_and_runs_through_typed_http_seams(
    client,
    operator_id,
    kind,
    fixture_items,
    config,
    expected_output_count,
):
    project = _single_operator_project(operator_id, kind, fixture_items, config)

    compile_response = await client.post(
        "/api/v1/workflows/compile",
        json={"project": project},
    )

    assert compile_response.status_code == 200
    compile_data = compile_response.json()["data"]
    assert compile_data["valid"] is True
    runtime = compile_data["plan"]["runtime"]
    operator_node = next(node for node in runtime["nodes"] if node["id"] == "operator")
    binding = operator_node["runtime"]["binding"]
    assert binding["binding_id"] == f"workflow.data.{kind}"
    assert binding["input"]["operatorId"] == operator_id
    assert binding["input"]["operatorKind"] == kind
    assert binding["input"]["inputPort"] == "recordCandidate[]"
    assert binding["input"]["outputPort"] == "recordCandidate[]"
    assert runtime["edges"][-1]["sourcePort"] == "out"
    assert runtime["edges"][-1]["targetPort"] == "in"
    if operator_id == "core.filter.quality":
        assert binding["input"]["config"] == {"minLength": 1}

    run_slug = operator_id.replace(".", "-")
    run_response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": f"run-{run_slug}",
            "traceId": f"trace-{run_slug}",
        },
    )
    assert run_response.status_code == 202
    assert run_response.json()["data"]["status"] == "completed"

    events = (
        await client.get(f"/api/v1/workflows/runs/run-{run_slug}/events")
    ).json()["data"]
    partial = next(
        event
        for event in events
        if event["nodeId"] == "operator" and event["eventType"] == "partial"
    )
    details = partial["details"]
    assert details["operatorId"] == operator_id
    assert details["bindingId"] == f"workflow.data.{kind}"
    assert details["inputItemCount"] == len(fixture_items)
    assert details["outputItemCount"] == expected_output_count
    assert details["metrics"]["inputCount"] == len(fixture_items)
    assert details["metrics"]["outputCount"] == expected_output_count
    assert details["lineage"]["nodeId"] == "operator"
    assert details["lineage"]["dependsOn"] == ["normalize"]


@pytest.mark.asyncio
async def test_capabilities_publish_one_aggregated_manifest_per_data_operator_kind(
    client,
):
    response = await client.get("/api/v1/workflows/capabilities")

    assert response.status_code == 200
    catalog = response.json()["data"]["catalog"]
    rows = [item for item in catalog if item["id"].startswith("intelligence.data.")]
    assert [row["id"] for row in rows] == list(_EXPECTED_OPERATOR_MANIFEST)
    assert len({row["id"] for row in rows}) == 4

    selected_keys = (
        "id",
        "operatorId",
        "kind",
        "label",
        "packId",
        "packVersion",
        "status",
        "readiness",
        "configKeys",
    )
    for row in rows:
        expected = _EXPECTED_OPERATOR_MANIFEST[row["id"]]
        operators = [
            {key: operator[key] for key in selected_keys}
            for operator in row["manifest"]["operators"]
        ]
        assert operators == expected
        assert row["manifest"]["operatorIds"] == [
            operator["operatorId"] for operator in expected
        ]
        assert row["manifest"]["packs"] == sorted(
            {operator["packId"] for operator in expected}
        )
        assert row["manifest"]["ports"] == {
            "inputs": [{"name": "in", "type": "recordCandidate[]"}],
            "outputs": [{"name": "out", "type": "recordCandidate[]"}],
        }
        assert row["status"] == "runnable"
        assert row["runtimeBinding"] == (
            f"workflow.data.{row['id'].rsplit('.', 1)[-1]}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("project", "code"),
    [
        (_minimal_operator_project(operator_id=None), "missing_data_operator_id"),
        (
            _minimal_operator_project(operator_id="data.generate.not-registered"),
            "unknown_data_operator",
        ),
        (
            _minimal_operator_project(
                catalog_kind="filter",
                operator_id="data.chunk",
            ),
            "data_operator_kind_mismatch",
        ),
    ],
)
async def test_compile_rejects_invalid_data_operator_contracts(client, project, code):
    response = await client.post("/api/v1/workflows/compile", json={"project": project})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["valid"] is False
    assert data["plan"] is None
    assert [(error["code"], error["path"]) for error in data["errors"]] == [
        (code, ["nodes", "operator", "params", "operatorId"])
    ]


@pytest.mark.asyncio
async def test_compile_rejects_operator_id_outside_data_operator_catalog(client):
    project = _minimal_operator_project()
    project["nodes"][0]["ui"] = {"catalogId": "intelligence.processing.normalize"}

    response = await client.post("/api/v1/workflows/compile", json={"project": project})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["valid"] is False
    assert [(error["code"], error["path"]) for error in data["errors"]] == [
        ("data_operator_catalog_required", ["nodes", "operator", "ui", "catalogId"])
    ]


@pytest.mark.asyncio
async def test_invalid_data_operator_config_is_a_failed_event_not_http_500(client):
    project = _dataflow_pipeline_project()
    chunk = next(node for node in project["nodes"] if node["id"] == "chunk")
    chunk["params"].update({"chunkSize": 0, "overlap": 0})

    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-dataflow-invalid-config",
            "traceId": "trace-dataflow-invalid-config",
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "failed"
    events = (
        await client.get("/api/v1/workflows/runs/run-dataflow-invalid-config/events")
    ).json()["data"]
    failed = next(
        event
        for event in events
        if event["nodeId"] == "chunk" and event["eventType"] == "failed"
    )
    assert failed["blockReason"]["code"] == "data_operator_execution_failed"
    assert failed["blockReason"]["source"] == "data_operator_runtime"
    assert failed["details"]["operatorId"] == "data.chunk"
    assert failed["details"]["errorType"] == "ValueError"
    assert "fixtureItems" not in str(failed["details"])


@pytest.mark.asyncio
async def test_data_operator_failure_event_is_redacted_after_json_serialization(
    client, monkeypatch
):
    secret = "candidate-value-must-not-leak"
    monkeypatch.setattr(
        "backend.workflow.opencli_hda_tracer.execute_data_operator",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": _dataflow_pipeline_project(),
            "runId": "run-dataflow-redacted-failure",
            "traceId": "trace-dataflow-redacted-failure",
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "failed"
    events_response = await client.get(
        "/api/v1/workflows/runs/run-dataflow-redacted-failure/events"
    )
    assert events_response.status_code == 200
    serialized_events = events_response.json()["data"]
    failed = next(
        event
        for event in serialized_events
        if event["nodeId"] == "project" and event["eventType"] == "failed"
    )
    assert failed["message"] == "Data operator execution failed"
    assert failed["blockReason"]["code"] == "data_operator_execution_failed"
    assert failed["blockReason"]["message"] == "Data operator execution failed"
    assert failed["details"] == {
        "bindingId": "workflow.data.refine",
        "operatorId": "data.project",
        "errorType": "RuntimeError",
    }
    assert secret not in str(serialized_events)


@pytest.mark.asyncio
async def test_nested_config_overrides_legacy_flat_operator_params(client):
    project = _dataflow_pipeline_project()
    chunk = next(node for node in project["nodes"] if node["id"] == "chunk")
    chunk["params"] = {
        "operatorId": "data.chunk",
        "chunkSize": 0,
        "config": {"chunkSize": 200, "overlap": 20},
    }

    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-dataflow-nested-config",
            "traceId": "trace-dataflow-nested-config",
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "completed"


@pytest.mark.asyncio
async def test_data_operator_capabilities_group_specs_by_kind(client, monkeypatch):
    monkeypatch.setattr(
        "backend.workflow.capability_projection.get_opencli_adapter_node_summary",
        lambda: {"total": 0},
    )
    response = await client.get("/api/v1/workflows/capabilities")

    assert response.status_code == 200
    catalog = response.json()["data"]["catalog"]
    for kind in ("generate", "filter", "evaluate", "refine"):
        rows = [row for row in catalog if row["id"] == f"intelligence.data.{kind}"]
        assert len(rows) == 1
        operators = rows[0]["manifest"]["operators"]
        assert operators
        assert all(
            {
                "id",
                "operatorId",
                "kind",
                "label",
                "packId",
                "packVersion",
                "status",
                "readiness",
                "configKeys",
            }
            <= operator.keys()
            and operator["kind"] == kind
            and operator["status"] == "runnable"
            and operator["readiness"] == "ready"
            for operator in operators
        )


@pytest.mark.asyncio
async def test_dataflow_pipeline_is_deterministic_at_http_seam(client):
    project = _dataflow_pipeline_project()
    first = deepcopy(project)
    second = deepcopy(project)

    for run_id, candidate in (
        ("run-dataflow-deterministic-a", first),
        ("run-dataflow-deterministic-b", second),
    ):
        response = await client.post(
            "/api/v1/workflows/runs",
            json={"project": candidate, "runId": run_id, "traceId": f"trace-{run_id}"},
        )
        assert response.status_code == 202
        assert response.json()["data"]["status"] == "completed"

    async def partials(run_id: str) -> dict[str, dict]:
        events = (
            await client.get(f"/api/v1/workflows/runs/{run_id}/events")
        ).json()["data"]
        return {
            event["nodeId"]: event["details"]
            for event in events
            if event["eventType"] == "partial"
            and event["nodeId"]
            in {
                "project",
                "chunk",
                "clean",
                "rule-filter",
                "deduplicate",
                "qa-extract",
                "training-format",
            }
        }

    first_partials = await partials("run-dataflow-deterministic-a")
    second_partials = await partials("run-dataflow-deterministic-b")
    for node_id in first_partials:
        assert first_partials[node_id]["metrics"] == second_partials[node_id]["metrics"]
        assert first_partials[node_id]["rejectedCount"] == second_partials[node_id][
            "rejectedCount"
        ]


@pytest.mark.asyncio
async def test_demand_draft_compiles_and_runs_the_native_dataflow_chain(
    client,
    db_session,
):
    response = await client.post(
        "/api/v1/workflows/demand-draft",
        json={
            "project": {
                "id": "wf-demand-dataflow",
                "name": "Demand DataFlow",
                "profile": "intelligence",
                "version": 1,
                "nodes": [
                    {
                        "id": "existing-fixture-source",
                        "kind": "source",
                        "capability": "fetch",
                        "adapter": "existing-fixture-adapter",
                        "params": {"fixtureItems": [{"content": "Existing input"}]},
                    }
                ],
                "edges": [],
                "adapters": [
                    {
                        "id": "existing-fixture-adapter",
                        "type": "source",
                        "provider": "fixture",
                        "mode": "fixture",
                        "config": {},
                    }
                ],
                "agentPermissions": {"canWriteInbox": True},
            },
            "text": "抓小红书 DataFlow 数据清洗",
            "locale": "zh-CN",
        },
    )

    assert response.status_code == 200
    draft = response.json()["data"]
    assert draft["valid"] is True
    assert draft["compile"]["valid"] is True
    project = draft["project"]
    drafted_operator_ids = [
        node["params"]["operatorId"]
        for node in draft["compile"]["plan"]["runtime"]["nodes"]
        if node["id"].endswith("-data")
    ]
    assert drafted_operator_ids == [
        "data.chunk",
        "text.clean",
        "text.deduplicate",
        "text.rule-filter",
        "text.statistics",
    ]
    drafted_versions = {
        node["params"]["operatorId"]: node["params"]["packVersion"]
        for node in draft["compile"]["plan"]["runtime"]["nodes"]
        if node["id"].endswith("-data")
    }
    assert drafted_versions == {
        "data.chunk": "1.0.0",
        "text.clean": "1.1.0",
        "text.deduplicate": "1.1.0",
        "text.rule-filter": "1.1.0",
        "text.statistics": "1.0.0",
    }

    source = next(node for node in project["nodes"] if node["id"] == "source-xiaohongshu")
    source["params"]["fixtureItems"] = [
        {
            "title": "DataFlow",
            "url": "https://example.com/dataflow-demand",
            "content": "<p>Clean   this DataFlow text.</p>",
        },
        {
            "title": "DataFlow",
            "url": "https://example.com/dataflow-demand",
            "content": "<p>Clean   this DataFlow text.</p>",
        },
    ]

    compile_response = await client.post(
        "/api/v1/workflows/compile",
        json={"project": project},
    )
    assert compile_response.status_code == 200
    assert compile_response.json()["data"]["valid"] is True

    run_response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-demand-dataflow",
            "traceId": "trace-demand-dataflow",
        },
    )
    assert run_response.status_code == 202
    assert run_response.json()["data"]["status"] == "completed"

    records = (await db_session.execute(select(CollectedRecord))).scalars().all()
    assert len(records) == 1
    assert records[0].normalized_data["content"] == "Clean this DataFlow text."
    assert records[0].normalized_data["dataflowStatistics"]["wordCount"] == 5


@pytest.mark.asyncio
async def test_rejected_candidate_ids_are_bounded_in_runtime_events(client):
    project = {
        "id": "wf-dataflow-rejection-bound",
        "name": "DataFlow rejection bound",
        "profile": "intelligence",
        "version": 1,
        "nodes": [
            {
                "id": "fixture-source",
                "kind": "source",
                "capability": "fetch",
                "adapter": "fixture-adapter",
                "params": {
                    "fixtureItems": [
                        {"id": f"source-{index}", "content": "x"} for index in range(105)
                    ]
                },
            },
            {
                "id": "normalize",
                "kind": "agent",
                "capability": "normalize",
                "params": {},
                "ui": {"catalogId": "intelligence.processing.normalize"},
            },
            {
                "id": "filter",
                "kind": "agent",
                "capability": "normalize",
                "params": {
                    "operatorId": "core.filter.quality",
                    "config": {"minChars": 2},
                },
                "ui": {"catalogId": "intelligence.data.filter"},
            },
        ],
        "edges": [
            {
                "id": "e-source-normalize",
                "source": "fixture-source",
                "target": "normalize",
                "sourcePort": "out",
                "targetPort": "in",
            },
            {
                "id": "e-normalize-filter",
                "source": "normalize",
                "target": "filter",
                "sourcePort": "out",
                "targetPort": "in",
            },
        ],
        "settings": {"maxItemsPerRun": 200},
        "adapters": [
            {
                "id": "fixture-adapter",
                "type": "source",
                "provider": "fixture",
                "mode": "fixture",
                "config": {},
            }
        ],
        "agentPermissions": {},
    }

    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-dataflow-rejection-bound",
            "traceId": "trace-dataflow-rejection-bound",
        },
    )
    assert response.status_code == 202

    events = (
        await client.get("/api/v1/workflows/runs/run-dataflow-rejection-bound/events")
    ).json()["data"]
    partial = next(
        event["details"]
        for event in events
        if event["nodeId"] == "filter" and event["eventType"] == "partial"
    )
    assert partial["rejectedCount"] == 105
    assert len(partial["rejectedCandidateIds"]) == 100
    assert partial["rejectedCandidateIdsTruncated"] is True


@pytest.mark.asyncio
async def test_missing_pack_version_compiles_to_the_legacy_v1_0_binding(client):
    project = _minimal_operator_project(
        catalog_kind="refine",
        operator_id="text.clean",
    )

    response = await client.post("/api/v1/workflows/compile", json={"project": project})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["valid"] is True
    runtime_node = data["plan"]["runtime"]["nodes"][0]
    assert runtime_node["runtime"]["binding"]["input"]["packVersion"] == "1.0.0"
    assert runtime_node["runtime"]["data_operator"]["pack_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_explicit_v1_1_pack_version_compiles_runs_and_is_traced_without_raw(
    client,
):
    secret_raw = "RAW-SECRET-MUST-NOT-ENTER-DATA-OPERATOR-EVENTS"
    project = _single_operator_project(
        "text.clean",
        "refine",
        [{"content": "  PINNED   VALUE  ", "secret": secret_raw}],
        {
            "fields": ["content"],
            "operations": ["removeExtraSpaces"],
        },
    )
    operator = next(node for node in project["nodes"] if node["id"] == "operator")
    operator["params"]["packVersion"] = "1.1.0"

    compile_response = await client.post(
        "/api/v1/workflows/compile",
        json={"project": project},
    )
    assert compile_response.status_code == 200
    compile_data = compile_response.json()["data"]
    assert compile_data["valid"] is True
    runtime_node = next(
        node
        for node in compile_data["plan"]["runtime"]["nodes"]
        if node["id"] == "operator"
    )
    assert runtime_node["runtime"]["binding"]["input"]["packVersion"] == "1.1.0"
    assert runtime_node["runtime"]["data_operator"]["pack_version"] == "1.1.0"

    run_response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-dataflow-v1-1-version-seam",
            "traceId": "trace-dataflow-v1-1-version-seam",
        },
    )
    assert run_response.status_code == 202
    assert run_response.json()["data"]["status"] == "completed"

    events = (
        await client.get(
            "/api/v1/workflows/runs/run-dataflow-v1-1-version-seam/events"
        )
    ).json()["data"]
    partial = next(
        event
        for event in events
        if event["nodeId"] == "operator" and event["eventType"] == "partial"
    )
    assert partial["details"]["operatorId"] == "text.clean"
    assert partial["details"]["packVersion"] == "1.1.0"
    assert secret_raw not in json.dumps(events, ensure_ascii=False)


@pytest.mark.asyncio
async def test_imported_dataflow_node_compiles_and_runs_without_provenance_in_config(
    client,
):
    source_sha = "f62aa1349e0ff14cb737a4cbda1945d04fde85bb"
    project = _single_operator_project(
        "text.clean",
        "refine",
        [{"content": "  MIXED   Case  "}],
        {"fields": ["content"], "operations": ["lowercase"]},
    )
    project["nodes"] = project["nodes"][:2]
    project["edges"] = project["edges"][:1]

    import_response = await client.post(
        "/api/v1/workflows/import/external-runtime",
        json={
            "project": project,
            "runtime": "dataflow",
            "name": "pinned-lowercase",
            "graph": {
                "sourceSha": source_sha,
                "nodes": [
                    {
                        "id": "lowercase",
                        "module": "general_text.refine.lowercase_refiner",
                        "class": "LowercaseRefiner",
                        "runConfig": {"input_key": "content"},
                    }
                ],
                "edges": [],
            },
        },
    )
    assert import_response.status_code == 200
    imported = import_response.json()["data"]["project"]
    imported["edges"].append(
        {
            "id": "e-normalize-lowercase",
            "source": "normalize",
            "target": "lowercase",
            "sourcePort": "out",
            "targetPort": "in",
        }
    )

    compile_response = await client.post(
        "/api/v1/workflows/compile",
        json={"project": imported},
    )
    assert compile_response.status_code == 200
    compile_data = compile_response.json()["data"]
    assert compile_data["valid"] is True
    runtime_node = next(
        node
        for node in compile_data["plan"]["runtime"]["nodes"]
        if node["id"] == "lowercase"
    )
    assert runtime_node["runtime"]["binding"]["input"]["config"] == {
        "fields": ["content"],
        "operations": ["lowercase"],
    }

    run_response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": imported,
            "runId": "run-imported-dataflow-node",
            "traceId": "trace-imported-dataflow-node",
        },
    )
    assert run_response.status_code == 202
    assert run_response.json()["data"]["status"] == "completed"


@pytest.mark.asyncio
async def test_compile_rejects_an_explicit_unsupported_pack_version(client):
    project = _minimal_operator_project(
        catalog_kind="refine",
        operator_id="text.clean",
    )
    project["nodes"][0]["params"]["packVersion"] = "9.9.9"

    response = await client.post("/api/v1/workflows/compile", json={"project": project})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["valid"] is False
    assert data["plan"] is None
    assert [(error["code"], error["path"]) for error in data["errors"]] == [
        (
            "unsupported_data_operator_version",
            ["nodes", "operator", "params", "packVersion"],
        )
    ]
