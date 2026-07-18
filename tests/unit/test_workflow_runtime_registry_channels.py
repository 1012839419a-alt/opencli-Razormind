"""Unit tests for the RSS / API channel bindings registered in
``backend.workflow.runtime_registry``.

These channels are now backed by dedicated ``iii.collector-{rss,api}.snapshot``
collector bindings (mirrors the OpenCLI binding's shape) so Canvas-authored
``source`` / ``fetch`` nodes that target the RSS / API DataSource channels
compile to a real backend worker / function instead of falling through the
generic ``workflow.source.fetch`` contract.

The tests exercise the resolver through the public ``resolve_runtime_metadata``
entry point so they stay coupled to the same dispatch the runtime exercises at
compile time.
"""

from __future__ import annotations

from backend.schemas.workflow import WorkflowAdapterBinding, WorkflowProjectNode
from backend.workflow.runtime_registry import (
    API_CHANNEL_BINDING_ID,
    API_CHANNEL_FUNCTION_ID,
    API_CHANNEL_WORKER,
    OPENCLI_BINDING_ID,
    RSS_CHANNEL_BINDING_ID,
    RSS_CHANNEL_FUNCTION_ID,
    RSS_CHANNEL_WORKER,
    resolve_runtime_metadata,
)


def _rss_node() -> WorkflowProjectNode:
    return WorkflowProjectNode(
        id="source-rss",
        kind="source",
        capability="fetch",
        adapter="channel-rss",
        params={"sourceId": "saved-rss-1"},
        ui={"catalogId": "intelligence.source.channel.rss"},
    )


def _rss_adapter(*, feed_url: str = "https://example.com/feed.xml") -> WorkflowAdapterBinding:
    return WorkflowAdapterBinding(
        id="channel-rss",
        type="source",
        provider="rss",
        mode="live",
        config={
            "channel": "rss",
            "channel_config": {
                "feed_url": feed_url,
                "max_entries": 20,
            },
        },
    )


def _api_node() -> WorkflowProjectNode:
    return WorkflowProjectNode(
        id="source-api",
        kind="source",
        capability="fetch",
        adapter="channel-api",
        params={"sourceId": "saved-api-1"},
        ui={"catalogId": "intelligence.source.channel.api"},
    )


def _api_adapter(
    *, endpoint: str = "v1/items"
) -> WorkflowAdapterBinding:
    return WorkflowAdapterBinding(
        id="channel-api",
        type="source",
        provider="api",
        mode="live",
        config={
            "channel": "api",
            "channel_config": {
                "base_url": "https://api.example.com",
                "endpoint": endpoint,
                "method": "GET",
            },
        },
    )


def test_rss_channel_resolves_to_dedicated_collector_binding() -> None:
    result = resolve_runtime_metadata(_rss_node(), _rss_adapter())
    binding = result["binding"]
    assert binding["binding_id"] == RSS_CHANNEL_BINDING_ID
    assert binding["runtime"] == "iii"
    assert binding["worker"] == RSS_CHANNEL_WORKER
    assert binding["function_id"] == RSS_CHANNEL_FUNCTION_ID
    assert binding["channel"] == "rss"
    assert binding["input"]["channelType"] == "rss"
    assert binding["input"]["sourceId"] == "saved-rss-1"
    assert binding["input"]["channelConfig"]["feed_url"] == "https://example.com/feed.xml"
    assert binding["input"]["outputPort"] == "items[]"
    # The runtime I/O contract is attached alongside the binding.
    assert binding["contract"]["bindingId"] == RSS_CHANNEL_BINDING_ID
    assert "feed_url" in binding["contract"]["configGate"]["required"]


def test_rss_channel_missing_feed_url_emits_missing_runtime_parameter() -> None:
    adapter = _rss_adapter(feed_url="")
    result = resolve_runtime_metadata(_rss_node(), adapter)
    assert "missing_runtime" in result
    missing = result["missing_runtime"]
    assert missing["code"] == "missing_runtime_parameter"
    assert missing["node_id"] == "source-rss"
    assert missing["provider"] == "rss"
    assert any("feed_url" in field for field in missing["required_params"])


def test_rss_channel_missing_adapter_emits_missing_runtime_binding() -> None:
    """A source/fetch node without an adapter binding cannot route through the
    RSS binding — the dispatcher falls through to the generic
    ``missing_runtime_binding`` reason (the same path any unbound source
    node takes). Lock this so the catch-all behavior doesn't change silently."""
    result = resolve_runtime_metadata(_rss_node(), None)
    assert "missing_runtime" in result
    assert result["missing_runtime"]["code"] == "missing_runtime_binding"


def test_rss_channel_matches_when_only_provider_is_set() -> None:
    """An adapter that only declares ``provider='rss'`` (no channel / channel_type
    in config — common for ad-hoc saved DataSources) must still route through the
    RSS binding."""
    adapter = WorkflowAdapterBinding(
        id="rss-provider-only",
        type="source",
        provider="rss",
        mode="live",
        config={"channel_config": {"feed_url": "https://example.com/feed.xml"}},
    )
    result = resolve_runtime_metadata(_rss_node(), adapter)
    assert result["binding"]["binding_id"] == RSS_CHANNEL_BINDING_ID


def test_api_channel_resolves_to_dedicated_collector_binding() -> None:
    result = resolve_runtime_metadata(_api_node(), _api_adapter())
    binding = result["binding"]
    assert binding["binding_id"] == API_CHANNEL_BINDING_ID
    assert binding["runtime"] == "iii"
    assert binding["worker"] == API_CHANNEL_WORKER
    assert binding["function_id"] == API_CHANNEL_FUNCTION_ID
    assert binding["channel"] == "api"
    assert binding["input"]["channelType"] == "api"
    assert binding["input"]["sourceId"] == "saved-api-1"
    assert (
        binding["input"]["channelConfig"]["base_url"] == "https://api.example.com"
    )
    assert binding["input"]["channelConfig"]["endpoint"] == "v1/items"
    assert binding["contract"]["bindingId"] == API_CHANNEL_BINDING_ID
    assert "base_url" in binding["contract"]["configGate"]["required"]
    assert "endpoint" in binding["contract"]["configGate"]["required"]


def test_api_channel_missing_endpoint_emits_missing_runtime_parameter() -> None:
    adapter = _api_adapter(endpoint="")
    result = resolve_runtime_metadata(_api_node(), adapter)
    assert "missing_runtime" in result
    missing = result["missing_runtime"]
    assert missing["code"] == "missing_runtime_parameter"
    assert missing["provider"] == "api"
    assert any("endpoint" in field for field in missing["required_params"])


def test_api_channel_missing_base_url_emits_missing_runtime_parameter() -> None:
    adapter = WorkflowAdapterBinding(
        id="channel-api-bad",
        type="source",
        provider="api",
        mode="live",
        config={"channel": "api", "channel_config": {"endpoint": "v1/items"}},
    )
    result = resolve_runtime_metadata(_api_node(), adapter)
    assert "missing_runtime" in result
    assert any("base_url" in field for field in result["missing_runtime"]["required_params"])


def test_api_channel_matches_when_only_provider_is_set() -> None:
    adapter = WorkflowAdapterBinding(
        id="api-provider-only",
        type="source",
        provider="api",
        mode="live",
        config={
            "channel_config": {
                "base_url": "https://api.example.com",
                "endpoint": "v1/items",
            }
        },
    )
    result = resolve_runtime_metadata(_api_node(), adapter)
    assert result["binding"]["binding_id"] == API_CHANNEL_BINDING_ID


def test_opencli_source_still_routes_through_opencli_binding() -> None:
    """Regression guard: adding the RSS / API predicates must not displace the
    OpenCLI binding for OpenCLI adapters — same node id + adapter as the
    pre-existing OpenCLI integration."""
    node = WorkflowProjectNode(
        id="source-bilibili",
        kind="source",
        capability="fetch",
        adapter="opencli-bilibili",
        params={"site": "bilibili", "command": "search"},
    )
    adapter = WorkflowAdapterBinding(
        id="opencli-bilibili",
        type="source",
        provider="opencli",
        mode="live",
        config={"channel": "opencli"},
    )
    result = resolve_runtime_metadata(node, adapter)
    assert result["binding"]["binding_id"] == OPENCLI_BINDING_ID


def test_rss_binding_ids_are_stable() -> None:
    """Stable binding IDs are the public contract compiled workflows ship to
    subscribers / Canvas UI; changing them is a break for everyone pinning
    against the workflow runtime registry. Lock the names so a typo doesn't
    silently rename them.
    """
    assert RSS_CHANNEL_BINDING_ID == "iii.collector-rss.snapshot"
    assert RSS_CHANNEL_WORKER == "collector-rss-channel"
    assert RSS_CHANNEL_FUNCTION_ID == "odp.collect::rss_feed_snapshot"
    assert API_CHANNEL_BINDING_ID == "iii.collector-api.snapshot"
    assert API_CHANNEL_WORKER == "collector-api-channel"
    assert API_CHANNEL_FUNCTION_ID == "odp.collect::api_request_snapshot"


def test_runtime_io_contract_registry_has_dedicated_rss_api_contracts() -> None:
    """The two new bindings must have runtime I/O contracts attached (same
    pattern as ``iii.collector-opencli.snapshot``); ``_attach_runtime_contract``
    strips the binding when no contract exists, so this is the gate that keeps
    them real."""
    from backend.workflow.runtime_contracts import runtime_io_contract_manifest

    assert runtime_io_contract_manifest(RSS_CHANNEL_BINDING_ID) is not None
    assert runtime_io_contract_manifest(API_CHANNEL_BINDING_ID) is not None
