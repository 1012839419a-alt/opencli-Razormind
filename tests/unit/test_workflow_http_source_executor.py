from __future__ import annotations

import httpx
import pytest

from backend.workflow.http_source_executor import execute_workflow_http_source


class _HTTPClient:
    def __init__(self, captured: dict[str, object]) -> None:
        self.captured = captured

    async def __aenter__(self) -> _HTTPClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self.captured.update({"method": method, "url": url, **kwargs})
        return httpx.Response(
            200,
            json={"data": {"items": [{"id": "item-1"}, {"id": "item-2"}]}},
            request=httpx.Request(method, url),
        )


@pytest.mark.asyncio
async def test_http_source_reads_request_configuration_from_node_params(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_guarded_client(url: str, **_kwargs: object):
        return _HTTPClient(captured), url

    monkeypatch.setattr(
        "backend.workflow.http_source_executor.guarded_async_client",
        fake_guarded_client,
    )

    result = await execute_workflow_http_source(
        {
            "provider": "http",
            "channelType": "http",
            "params": {
                "url": "https://api.example.cn/v1/items",
                "method": "GET",
                "headers": {"X-Client": "opencli"},
                "query": {"limit": 2},
                "resultPath": "data.items",
            },
        },
        allowed_domains=["api.example.cn"],
        max_items=20,
    )

    assert result is not None
    assert result.items == [{"id": "item-1"}, {"id": "item-2"}]
    assert result.result_path == "data.items"
    assert captured["headers"] == {"X-Client": "opencli"}
    assert captured["params"] == {"limit": 2}
