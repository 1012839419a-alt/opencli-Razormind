from __future__ import annotations

import importlib

import httpx
from fastapi.testclient import TestClient
from starlette.requests import Request


def _request(path: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": path,
            "query_string": b"",
            "headers": headers,
            "server": ("proof-delivery-proxy", 8000),
        }
    )


def test_delivery_proxy_requires_authenticated_mode_changes(monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "proof-token")
    proxy = importlib.import_module("tests.acceptance.fault_tools.proof_delivery_proxy")
    proxy._mode = proxy.DeliveryProxyMode.PASS_THROUGH
    client = TestClient(proxy.app)

    assert client.post("/_gate/delivery", json={"mode": "corrupt_mac"}).status_code == 401
    response = client.post(
        "/_gate/delivery",
        json={"mode": "corrupt_mac"},
        headers={"X-API-Token": "proof-token"},
    )

    assert response.status_code == 200
    assert proxy._mode is proxy.DeliveryProxyMode.CORRUPT_MAC


def test_delivery_proxy_corrupts_only_delivery_mac_and_preserves_other_headers(monkeypatch):
    proxy = importlib.import_module("tests.acceptance.fault_tools.proof_delivery_proxy")
    proxy._mode = proxy.DeliveryProxyMode.CORRUPT_MAC
    delivered: dict[str, object] = {}

    async def fake_forward(request: Request, path: str) -> httpx.Response:
        delivered["path"] = path
        delivered["headers"] = proxy._forward_headers(request)
        return httpx.Response(200, json={"receipt": {"version": "v2"}})

    monkeypatch.setattr(proxy, "_forward", fake_forward)
    client = TestClient(proxy.app)
    response = client.post(
        "/api/v1/controlled-receiver/v2/deliver",
        content=b"{}",
        headers={"X-Controlled-Receiver-Mac": "original", "X-Retained": "value"},
    )

    assert response.status_code == 200
    assert delivered["path"] == "/api/v1/controlled-receiver/v2/deliver"
    assert delivered["headers"]["x-retained"] == "value"
    assert delivered["headers"]["X-Controlled-Receiver-Mac"] == "sha256=corrupted-by-proof-proxy"

    status_headers = proxy._forward_headers(
        _request(
            "/api/v1/controlled-receiver/v2/status",
            [(b"x-controlled-receiver-mac", b"original")],
        )
    )
    assert status_headers["x-controlled-receiver-mac"] == "original"
