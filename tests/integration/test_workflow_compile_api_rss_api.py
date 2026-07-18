"""HTTP-seam compile tests for RSS / API source / fetch nodes."""

import pytest


def _assert_binding_includes(actual: dict, expected: dict) -> None:
    for key, value in expected.items():
        assert actual.get(key) == value
    if "contract" in actual:
        assert actual["contract"]["bindingId"] == expected["binding_id"]


def _channel_source_workflow_project(*, channel: str, source_id: str) -> dict:
    """Helper: a 2-node workflow (source/fetch + normalize) targeting either the
    RSS or API DataSource-backed channel. Stays self-contained so each test
    declares which channel + saved source it wants."""
    if channel not in {"rss", "api"}:
        raise ValueError(f"unsupported channel {channel!r} for compile fixture")
    channel_config = (
        {"feed_url": "https://example.com/feed.xml", "max_entries": 20}
        if channel == "rss"
        else {
            "base_url": "https://api.example.com",
            "endpoint": "v1/items",
            "method": "GET",
        }
    )
    return {
        "id": f"wf-channel-{channel}",
        "name": f"{channel.upper()} source compile",
        "profile": "intelligence",
        "version": 1,
        "nodes": [
            {
                "id": f"source-{channel}",
                "kind": "source",
                "capability": "fetch",
                "adapter": f"channel-{channel}",
                "params": {"sourceId": source_id},
                "ui": {"catalogId": f"intelligence.source.channel.{channel}"},
            },
            {
                "id": "normalize-items",
                "kind": "agent",
                "capability": "normalize",
                "params": {"language": "zh-CN"},
            },
        ],
        "edges": [
            {
                "id": f"e-source-{channel}-normalize",
                "source": f"source-{channel}",
                "target": "normalize-items",
            }
        ],
        "adapters": [
            {
                "id": f"channel-{channel}",
                "type": "source",
                "provider": channel,
                "mode": "live",
                "config": {"channel": channel, "channel_config": channel_config},
            }
        ],
        "agentPermissions": {
            "canFetchNetwork": True,
            "canSendNotifications": False,
            "canWriteInbox": True,
        },
    }


@pytest.mark.asyncio
async def test_compile_resolves_rss_source_to_iii_runtime_binding(client):
    project = _channel_source_workflow_project(channel="rss", source_id="rss-feed-1")

    response = await client.post("/api/v1/workflows/compile", json={"project": project})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["valid"] is True
    runtime = data["plan"]["runtime"]
    source_node = next(node for node in runtime["nodes"] if node["id"] == "source-rss")
    _assert_binding_includes(source_node["runtime"]["binding"], {
        "status": "bound",
        "binding_id": "iii.collector-rss.snapshot",
        "runtime": "iii",
        "worker": "collector-rss-channel",
        "function_id": "odp.collect::rss_feed_snapshot",
        "channel": "rss",
    })
    binding_input = source_node["runtime"]["binding"]["input"]
    assert binding_input["channelType"] == "rss"
    assert binding_input["sourceId"] == "rss-feed-1"
    assert binding_input["channelConfig"]["feed_url"] == "https://example.com/feed.xml"
    assert source_node["runtime"]["binding"]["contract"]["bindingId"] == (
        "iii.collector-rss.snapshot"
    )


@pytest.mark.asyncio
async def test_compile_resolves_api_source_to_iii_runtime_binding(client):
    project = _channel_source_workflow_project(channel="api", source_id="api-endpoint-1")

    response = await client.post("/api/v1/workflows/compile", json={"project": project})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["valid"] is True
    runtime = data["plan"]["runtime"]
    source_node = next(node for node in runtime["nodes"] if node["id"] == "source-api")
    _assert_binding_includes(source_node["runtime"]["binding"], {
        "status": "bound",
        "binding_id": "iii.collector-api.snapshot",
        "runtime": "iii",
        "worker": "collector-api-channel",
        "function_id": "odp.collect::api_request_snapshot",
        "channel": "api",
    })
    binding_input = source_node["runtime"]["binding"]["input"]
    assert binding_input["channelType"] == "api"
    assert binding_input["sourceId"] == "api-endpoint-1"
    assert binding_input["channelConfig"]["base_url"] == "https://api.example.com"
    assert binding_input["channelConfig"]["endpoint"] == "v1/items"
    assert source_node["runtime"]["binding"]["contract"]["bindingId"] == (
        "iii.collector-api.snapshot"
    )


@pytest.mark.asyncio
async def test_compile_marks_rss_source_without_feed_url_as_missing_runtime_parameter(
    client,
):
    project = _channel_source_workflow_project(channel="rss", source_id="rss-feed-2")
    project["adapters"] = [
        {
            "id": "channel-rss",
            "type": "source",
            "provider": "rss",
            "mode": "live",
            "config": {"channel": "rss", "channel_config": {"max_entries": 5}},
        }
    ]

    response = await client.post("/api/v1/workflows/compile", json={"project": project})

    assert response.status_code == 200
    source_node = next(
        node
        for node in response.json()["data"]["plan"]["runtime"]["nodes"]
        if node["id"] == "source-rss"
    )
    assert "binding" not in source_node["runtime"]
    missing = source_node["runtime"]["missing_runtime"]
    assert missing["code"] == "missing_runtime_parameter"
    assert missing["provider"] == "rss"
    assert any("feed_url" in field for field in missing["required_params"])


@pytest.mark.asyncio
async def test_compile_marks_api_source_without_endpoint_as_missing_runtime_parameter(
    client,
):
    project = _channel_source_workflow_project(channel="api", source_id="api-endpoint-2")
    project["adapters"] = [
        {
            "id": "channel-api",
            "type": "source",
            "provider": "api",
            "mode": "live",
            "config": {
                "channel": "api",
                "channel_config": {"base_url": "https://api.example.com"},
            },
        }
    ]

    response = await client.post("/api/v1/workflows/compile", json={"project": project})

    assert response.status_code == 200
    source_node = next(
        node
        for node in response.json()["data"]["plan"]["runtime"]["nodes"]
        if node["id"] == "source-api"
    )
    assert "binding" not in source_node["runtime"]
    missing = source_node["runtime"]["missing_runtime"]
    assert missing["code"] == "missing_runtime_parameter"
    assert missing["provider"] == "api"
    assert any("endpoint" in field for field in missing["required_params"])
