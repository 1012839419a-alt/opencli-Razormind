from __future__ import annotations

import json

import pytest

from backend.workflow import realtime_market_executor


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


class _Opener:
    def __init__(self, payload: dict[str, object]) -> None:
        self._response = _Response(payload)
        self.calls: list[tuple[object, float]] = []

    def open(self, request: object, *, timeout: float) -> _Response:
        self.calls.append((request, timeout))
        return self._response


def test_execute_okx_market_ticker_snapshot_projects_a_ticker_response(monkeypatch) -> None:
    opener = _Opener(
        {
            "code": "0",
            "data": [
                {
                    "instId": "BTC-USDT",
                    "ts": "1000120",
                    "last": "100000",
                    "bidPx": "99999",
                    "askPx": "100001",
                }
            ],
        }
    )
    proxy_urls: list[str | None] = []
    validated_urls: list[str] = []
    times = iter((1000.0, 1000.123, 1000.456))

    def build_opener(proxy: str | None) -> _Opener:
        proxy_urls.append(proxy)
        return opener

    monkeypatch.setattr(realtime_market_executor, "_build_opener", build_opener)
    monkeypatch.setattr(
        realtime_market_executor,
        "validate_public_url",
        lambda url: validated_urls.append(url),
    )
    monkeypatch.setattr(realtime_market_executor.time, "time", lambda: next(times))

    event = realtime_market_executor.execute_okx_market_ticker_snapshot(
        {"inst_id": "BTC-USDT", "proxyUrl": "http://proxy.test:8080", "timeoutSeconds": 4}
    )

    request, timeout = opener.calls[0]
    assert request.full_url == "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT"
    assert timeout == 4.0
    assert proxy_urls == ["http://proxy.test:8080"]
    assert validated_urls == ["http://proxy.test:8080"]
    assert event["instId"] == "BTC-USDT"
    assert event["eventTime"] == "1970-01-01T00:16:40.120000+00:00"
    assert event["latencyMs"] == 3
    assert event["request"] == {
        "url": "https://www.okx.com/api/v5/market/ticker",
        "instId": "BTC-USDT",
        "proxy": "configured",
        "durationMs": 456,
    }
    assert event["market"]["last"] == "100000"


def test_execute_okx_market_ticker_snapshot_rejects_unsuccessful_response(monkeypatch) -> None:
    monkeypatch.setattr(
        realtime_market_executor,
        "_build_opener",
        lambda _: _Opener({"code": "51000", "data": []}),
    )

    with pytest.raises(realtime_market_executor.RealtimeMarketExecutionError, match="non-success"):
        realtime_market_executor.execute_okx_market_ticker_snapshot({})
