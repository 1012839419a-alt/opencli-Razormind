from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from backend.auth.manager import (
    AuthManager,
    CredentialResolutionError,
    CredentialResolutionUnavailableError,
)
from backend.channels.api_channel import ApiChannel
from backend.channels.base import AuthContext, FetchContext, FetchResult
from backend.schemas.workflow import CollectedItemV1, CollectorNodeParams, CompiledWorkflowNode
from backend.workflow import opencli_hda_tracer as tracer


def _collector_node(*sources: dict, execution: dict | None = None) -> CompiledWorkflowNode:
    return CompiledWorkflowNode(
        id="collector",
        kind="source",
        capability="fetch",
        params={},
        runtime={
            "binding": {
                "binding_id": "collection.source.api",
                "input": {
                    "collectorType": "api",
                    "sources": list(sources),
                    "execution": execution or {},
                },
            }
        },
    )


@pytest.mark.parametrize(
    ("container", "key"),
    [
        ("headers", "X-API-Key"),
        ("query", "xapikey"),
        ("body", "access_token"),
        ("body", "access-token"),
    ],
)
def test_sensitive_key_variants_are_rejected_recursively(container: str, key: str):
    source = {
        "kind": "api",
        "sourceId": "api",
        "url": "https://example.com/items",
        container: {"nested": {key: "plaintext"}},
    }

    with pytest.raises(ValidationError, match="forbidden persisted fields"):
        CollectorNodeParams.model_validate({"sources": [source]})


def test_collector_api_rejects_write_methods_and_resource_overages():
    with pytest.raises(ValidationError):
        CollectorNodeParams.model_validate(
            {
                "sources": [
                    {
                        "kind": "api",
                        "sourceId": "api",
                        "url": "https://example.com/items",
                        "method": "POST",
                    }
                ]
            }
        )

    for execution in (
        {"concurrency": 17},
        {"timeoutMs": 120_001},
        {"retry": {"maxAttempts": 6}},
        {"retry": {"maxAttempts": 2, "backoffMs": 30_001}},
    ):
        with pytest.raises(ValidationError):
            CollectorNodeParams.model_validate({"execution": execution})

    with pytest.raises(ValidationError, match="execution budget"):
        CollectorNodeParams.model_validate(
            {
                "execution": {
                    "timeoutMs": 120_000,
                    "retry": {"maxAttempts": 5, "backoffMs": 30_000},
                }
            }
        )

    sources = [
        {
            "kind": "api",
            "sourceId": f"api-{index}",
            "url": "https://example.com/items",
        }
        for index in range(65)
    ]
    with pytest.raises(ValidationError):
        CollectorNodeParams.model_validate({"sources": sources})


def test_blank_published_at_is_normalized_to_none():
    item = CollectedItemV1.model_validate(
        {
            "itemId": "item",
            "sourceId": "source",
            "sourceType": "api",
            "publishedAt": "   ",
            "fetchedAt": "2026-07-24T12:00:00Z",
        }
    )

    assert item.publishedAt is None


def test_cli_collector_rejects_resolved_write_adapter(monkeypatch):
    monkeypatch.setattr(
        "backend.workflow.opencli_adapter_nodes.resolve_opencli_adapter_node",
        lambda _adapter_id: SimpleNamespace(
            access="write",
            site="example",
            command="delete",
        ),
    )

    with pytest.raises(ValueError, match="write_access_forbidden"):
        tracer._collector_channel_config(
            {
                "kind": "cli",
                "sourceId": "cli",
                "adapterNodeId": "opencli.adapter.example.delete",
            },
            "cli",
        )


def test_collector_api_runtime_defense_rejects_write_method():
    with pytest.raises(ValueError, match="collector_api_method_not_allowed"):
        tracer._collector_channel_config(
            {
                "kind": "api",
                "sourceId": "api",
                "url": "https://example.com/items",
                "method": "PATCH",
            },
            "api",
        )
    with pytest.raises(ValueError, match="collector_plaintext_credential_forbidden"):
        tracer._collector_channel_config(
            {
                "kind": "api",
                "sourceId": "api",
                "url": "https://example.com/items",
                "body": {"nested": {"x-api-key": "plaintext"}},
            },
            "api",
        )


@pytest.mark.asyncio
async def test_credential_reference_resolves_to_ephemeral_auth_not_source_id(monkeypatch):
    resolve = AsyncMock(return_value={"access_token": "runtime-secret"})
    monkeypatch.setattr(AuthManager, "resolve", resolve)

    auth = await AuthManager().resolve_reference_context(
        "credential://source-a",
        "bearer",
    )

    resolve.assert_awaited_once_with("source-a")
    assert auth == AuthContext(
        kind="bearer",
        headers={"Authorization": "Bearer runtime-secret"},
    )
    with pytest.raises(CredentialResolutionError, match="invalid credential reference"):
        await AuthManager().resolve_reference_context("source-a", "bearer")


@pytest.mark.asyncio
async def test_collector_injects_resolved_auth_without_leaking_ref_or_secret(
    monkeypatch,
):
    seen = {}

    class Channel:
        async def fetch(self, ctx):
            seen["ctx"] = ctx
            return FetchResult(items=[{"title": "ok"}])

    resolve = AsyncMock(
        return_value=AuthContext(
            kind="bearer",
            headers={"Authorization": "Bearer runtime-secret"},
        )
    )
    monkeypatch.setattr(AuthManager, "resolve_reference_context", resolve)
    monkeypatch.setattr("backend.channels.registry.get_channel", lambda _name: Channel())

    source = {
        "kind": "api",
        "sourceId": "api",
        "url": "https://example.com/items",
        "credentialRef": "credential://source-a",
        "credentialScheme": "bearer",
    }
    result = await tracer._collect_source_once(source, "api")

    assert result == [{"title": "ok"}]
    resolve.assert_awaited_once_with("credential://source-a", "bearer")
    assert seen["ctx"].source_id is None
    assert seen["ctx"].auth.headers["Authorization"] == "Bearer runtime-secret"
    assert "credentialRef" not in seen["ctx"].config
    assert "runtime-secret" not in repr(seen["ctx"].config)


@pytest.mark.asyncio
async def test_api_channel_consumes_runtime_auth_and_head_has_no_json_body(
    monkeypatch,
):
    channel = ApiChannel()
    response = SimpleNamespace(status_code=204)
    send = AsyncMock(return_value=response)
    legacy_auth = AsyncMock(side_effect=AssertionError("legacy auth must not run"))
    monkeypatch.setattr(channel, "_send", send)
    monkeypatch.setattr(channel, "_resolve_auth_headers", legacy_auth)
    monkeypatch.setattr(
        "backend.channels.api_channel.avalidate_public_url",
        AsyncMock(return_value="https://example.com/items"),
    )

    result = await channel.fetch(
        FetchContext(
            config={
                "base_url": "https://example.com/items",
                "endpoint": "",
                "method": "HEAD",
            },
            params={},
            auth=AuthContext(
                kind="bearer",
                headers={"Authorization": "Bearer runtime-secret"},
            ),
            http=object(),
        )
    )

    assert result.items == []
    assert result.metadata["status_code"] == 204
    assert send.await_args.args[5] == {
        "Authorization": "Bearer runtime-secret"
    }
    legacy_auth.assert_not_awaited()


@pytest.mark.asyncio
async def test_credential_resolution_unavailable_fails_closed_before_channel(
    monkeypatch,
):
    monkeypatch.setattr(
        AuthManager,
        "resolve_reference_context",
        AsyncMock(
            side_effect=CredentialResolutionUnavailableError(
                "credential_resolution_unavailable"
            )
        ),
    )
    get_channel = AsyncMock()
    monkeypatch.setattr("backend.channels.registry.get_channel", get_channel)

    with pytest.raises(
        CredentialResolutionUnavailableError,
        match="credential_resolution_unavailable",
    ):
        await tracer._collect_source_once(
            {
                "kind": "api",
                "sourceId": "api",
                "url": "https://example.com/items",
                "credentialRef": "credential://source-a",
                "credentialScheme": "bearer",
            },
            "api",
        )
    get_channel.assert_not_called()


def test_output_redaction_covers_common_sensitive_variants():
    sanitized = tracer._sanitize_collector_output(
        {
            "x-api-key": "secret",
            "nested": {
                "access_token": "secret",
                "access-token": "secret",
                "safe": "value",
            },
        }
    )

    assert sanitized == {"nested": {"safe": "value"}}


@pytest.mark.asyncio
async def test_exponential_backoff_is_capped_at_thirty_seconds(monkeypatch):
    sleeps: list[float] = []

    async def fail(_source, _source_type):
        raise TimeoutError("retry")

    async def record_sleep(delay: float):
        sleeps.append(delay)

    monkeypatch.setattr(tracer, "_collect_source_once", fail)
    monkeypatch.setattr(tracer.asyncio, "sleep", record_sleep)

    _, results = await tracer._execute_collector_source_node(
        _collector_node(
            {
                "kind": "api",
                "sourceId": "api",
                "url": "https://example.com/items",
            },
            execution={
                "timeoutMs": 1,
                "retry": {"maxAttempts": 5, "backoffMs": 30_000},
            },
        )
    )

    assert results[0]["attempts"] == 5
    assert sleeps == [30.0, 30.0, 30.0, 30.0]
