from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.schemas.workflow import (
    CollectorNodeParams,
    CollectorOutputV1,
    WorkflowProjectNode,
    validate_collector_node_params,
)
from backend.workflow.runtime_contracts import (
    collector_runtime_contract,
    normalize_collector_runtime_params,
    runtime_io_contract_manifest,
)


@pytest.mark.parametrize(
    ("catalog_id", "source"),
    [
        (
            "collection.source.web",
            {
                "kind": "web",
                "sourceId": "web-1",
                "url": "https://example.com/articles",
                "selector": "article",
            },
        ),
        (
            "collection.source.api",
            {
                "kind": "api",
                "sourceId": "api-1",
                "url": "https://api.example.com/items",
                "query": {"limit": 20},
                "credentialRef": "credential://api-example",
                "credentialScheme": "bearer",
            },
        ),
        (
            "collection.source.rss",
            {
                "kind": "rss",
                "sourceId": "rss-1",
                "feedUrl": "https://example.com/feed.xml",
                "itemLimit": 50,
            },
        ),
        (
            "collection.source.cli",
            {
                "kind": "cli",
                "sourceId": "cli-1",
                "adapterNodeId": "opencli.adapter.example.list",
                "args": {"limit": 20, "published": True},
            },
        ),
    ],
)
def test_collector_node_params_accept_each_source_kind(catalog_id, source):
    params = validate_collector_node_params(
        catalog_id,
        {
            "version": 1,
            "execution": {
                "concurrency": 2,
                "timeoutMs": 10_000,
                "retry": {"maxAttempts": 3, "backoffMs": 250},
            },
            "sources": [source],
        },
    )

    assert params.version == 1
    assert params.sources[0].kind == catalog_id.rsplit(".", 1)[-1]


def test_collector_node_type_rejects_cross_kind_source():
    with pytest.raises(ValueError, match="only accepts web sources"):
        validate_collector_node_params(
            "collection.source.web",
            {
                "version": 1,
                "sources": [
                    {
                        "kind": "api",
                        "sourceId": "wrong-kind",
                        "url": "https://api.example.com/items",
                    }
                ],
            },
        )


def test_workflow_node_api_boundary_validates_collector_catalog_kind():
    with pytest.raises(ValidationError, match="only accepts web sources"):
        WorkflowProjectNode.model_validate(
            {
                "id": "collector",
                "kind": "source",
                "capability": "fetch",
                "ui": {"catalogId": "collection.source.web"},
                "params": {
                    "version": 1,
                    "sources": [
                        {
                            "kind": "rss",
                            "sourceId": "wrong-kind",
                            "feedUrl": "https://example.com/feed.xml",
                        }
                    ],
                },
            }
        )


def test_collector_source_ids_must_be_stable_and_unique():
    source = {
        "kind": "rss",
        "sourceId": "duplicate",
        "feedUrl": "https://example.com/feed.xml",
    }
    with pytest.raises(ValidationError, match="sourceId values must be unique"):
        CollectorNodeParams.model_validate({"version": 1, "sources": [source, source]})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("shell", "bash"),
        ("commandLine", "curl https://example.com"),
        ("scriptText", "print('unsafe')"),
        ("rawCommand", "example list"),
        ("token", "plain-token"),
        ("password", "plain-password"),
        ("cookie", "session=plain"),
        ("authorization", "Bearer plain"),
    ],
)
def test_cli_rejects_commands_and_plaintext_credentials_recursively(field, value):
    with pytest.raises(ValidationError, match="forbidden persisted fields"):
        CollectorNodeParams.model_validate(
            {
                "version": 1,
                "sources": [
                    {
                        "kind": "cli",
                        "sourceId": "cli-unsafe",
                        "adapterNodeId": "opencli.adapter.example.list",
                        "args": {"nested": {field: value}},
                    }
                ],
            }
        )


def test_api_rejects_plain_authorization_but_accepts_credential_reference():
    with pytest.raises(ValidationError, match="forbidden persisted fields"):
        CollectorNodeParams.model_validate(
            {
                "version": 1,
                "sources": [
                    {
                        "kind": "api",
                        "sourceId": "api-unsafe",
                        "url": "https://api.example.com/items",
                        "headers": {"Authorization": "Bearer plain"},
                    }
                ],
            }
        )

    params = CollectorNodeParams.model_validate(
        {
            "version": 1,
            "sources": [
                {
                    "kind": "api",
                    "sourceId": "api-safe",
                    "url": "https://api.example.com/items",
                    "credentialRef": "credential://api-example",
                    "credentialScheme": "bearer",
                }
            ],
        }
    )
    assert params.sources[0].credentialRef == "credential://api-example"


def test_credential_reference_and_scheme_must_be_configured_together():
    with pytest.raises(
        ValidationError,
        match="credentialRef and credentialScheme must be configured together",
    ):
        CollectorNodeParams.model_validate(
            {
                "version": 1,
                "sources": [
                    {
                        "kind": "api",
                        "sourceId": "api-missing-scheme",
                        "url": "https://api.example.com/items",
                        "credentialRef": "credential://api-example",
                    }
                ],
            }
        )


@pytest.mark.parametrize("kind", ["web", "rss", "cli"])
def test_non_api_collectors_reject_unsupported_credential_references(kind):
    source = {
        "kind": kind,
        "sourceId": f"{kind}-credential",
        "credentialRef": "credential://source-a",
        "credentialScheme": "bearer",
    }
    if kind == "web":
        source.update(url="https://example.com", fetchMode="auto")
    elif kind == "rss":
        source.update(feedUrl="https://example.com/feed.xml")
    else:
        source.update(adapterNodeId="opencli.adapter.example.list", args={})

    with pytest.raises(
        ValidationError,
        match="credential references are currently supported only for api collectors",
    ):
        CollectorNodeParams.model_validate({"version": 1, "sources": [source]})


def test_legacy_site_command_normalization_is_read_only_and_deterministic():
    saved_params = {
        "site": "Example News",
        "command": "latest-items",
        "args": {"limit": 20},
        "format": "json",
    }
    original = deepcopy(saved_params)

    first = normalize_collector_runtime_params("collection.source.cli", saved_params)
    second = normalize_collector_runtime_params("collection.source.cli", saved_params)

    assert saved_params == original
    assert first == second
    assert first.version == 1
    assert first.sources[0].sourceId.startswith("legacy-")
    assert first.sources[0].adapterNodeId == (
        "opencli.adapter.example-news.latest-items"
    )
    assert first.sources[0].args == {"limit": 20}
    normalized_dump = first.model_dump(mode="json")
    assert "site" not in normalized_dump["sources"][0]
    assert "command" not in normalized_dump["sources"][0]


def test_collector_output_keeps_published_and_fetched_times_independent():
    output = CollectorOutputV1.model_validate(
        {
            "items": [
                {
                    "itemId": "item-1",
                    "sourceId": "rss-1",
                    "sourceType": "rss",
                    "publishedAt": None,
                    "fetchedAt": "2026-07-24T12:00:00Z",
                    "lineage": {"feedUrl": "https://example.com/feed.xml"},
                }
            ],
            "sourceResults": [
                {
                    "sourceId": "rss-1",
                    "status": "completed",
                    "itemCount": 1,
                    "attempts": 1,
                    "startedAt": "2026-07-24T11:59:59Z",
                    "finishedAt": "2026-07-24T12:00:00Z",
                }
            ],
        }
    )

    assert output.items[0].publishedAt is None
    assert output.items[0].fetchedAt == "2026-07-24T12:00:00Z"
    assert output.sourceResults[0].itemCount == 1


def test_failed_source_result_requires_structured_error():
    with pytest.raises(ValidationError, match="requires error details"):
        CollectorOutputV1.model_validate(
            {
                "sourceResults": [
                    {
                        "sourceId": "web-1",
                        "status": "failed",
                        "itemCount": 0,
                        "attempts": 1,
                        "startedAt": "2026-07-24T11:59:59Z",
                        "finishedAt": "2026-07-24T12:00:00Z",
                    }
                ]
            }
        )


def test_runtime_contracts_expose_unified_collector_output():
    for kind in ("web", "api", "rss", "cli"):
        manifest = collector_runtime_contract(kind).to_manifest()
        assert manifest["bindingId"] == f"collection.source.{kind}"
        assert manifest["outputShape"]["ports"] == [
            {"name": "out", "type": "CollectorOutputV1"}
        ]
        assert manifest["inputShape"]["params"] == ["version", "execution", "sources"]


def test_merge_runtime_contract_is_variadic_with_legacy_aliases():
    manifest = runtime_io_contract_manifest("workflow.flow.merge")

    assert manifest is not None
    assert manifest["inputShape"]["ports"] == [
        {
            "name": "in",
            "type": "CollectorMergeInputV1",
            "cardinality": "many",
            "minConnections": 1,
            "legacyAliases": ["in1", "in2"],
        }
    ]
    assert "strategy" not in manifest["inputShape"]["params"]
