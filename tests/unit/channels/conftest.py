"""Shared fixtures for channel unit tests."""

import pytest

from backend.channels import rss_channel


@pytest.fixture
def mock_rss_public_client(monkeypatch):
    """Keep mocked RSS fetches independent of host DNS policy."""

    async def guarded_client(feed_url: str, **client_kwargs):
        return rss_channel.httpx.AsyncClient(**client_kwargs), feed_url

    monkeypatch.setattr(rss_channel, "guarded_async_client", guarded_client)
