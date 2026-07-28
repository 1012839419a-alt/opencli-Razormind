from __future__ import annotations

import json

import httpx
import pytest

from backend.image_studio.adapter import (
    InvokeAIAdapter,
    InvokeJobBinding,
    InvokeQueueState,
)
from backend.image_studio.invoke_client import (
    ALLOWED_INVOKE_OPERATIONS,
    InvokeAIClient,
    InvokeAIClientError,
    InvokeAIConnection,
)


def _transport(handler):
    return httpx.MockTransport(handler)


def _response(status_code: int, payload: object) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def test_client_surface_is_an_explicit_allowlist_without_a_proxy_escape_hatch():
    assert ALLOWED_INVOKE_OPERATIONS == frozenset(
        {
            "enqueue_batch",
            "get_queue_item",
            "cancel_queue_item",
            "stream_image",
            "list_models",
            "list_missing_models",
        }
    )
    assert not hasattr(InvokeAIClient, "proxy")
    assert not hasattr(InvokeAIClient, "request")


async def test_enqueue_compiles_an_executable_graph_and_uses_only_queue_allowlist():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.method == "POST"
        assert request.url.path == "/api/v1/queue/default/enqueue_batch"
        assert request.headers["authorization"] == "Bearer sidecar-jwt"
        assert request.headers["idempotency-key"] == binding.idempotency_key
        payload = json.loads(request.content)
        assert payload == {
            "batch": {
                "graph": {"id": "graph-1", "nodes": {"noise": {"type": "noise"}}},
                "data": [[{"node_path": "prompt", "field_name": "value", "items": ["cat"]}]],
                "runs": 1,
            },
            "prepend": False,
        }
        return _response(
            200,
            {"batch": {"batch_id": "batch-7"}, "item_ids": [41], "session_id": "session-9"},
        )

    binding = InvokeJobBinding.create(run_id="run-1", node_id="image-1", attempt=2)
    client = InvokeAIClient(
        InvokeAIConnection("http://invoke.internal:9090", jwt="sidecar-jwt"),
        transport=_transport(handler),
    )
    adapter = InvokeAIAdapter(client)

    submitted = await adapter.submit(
        binding,
        executable_graph={"id": "graph-1", "nodes": {"noise": {"type": "noise"}}},
        batch_data=[[{"node_path": "prompt", "field_name": "value", "items": ["cat"]}]],
    )

    assert len(seen) == 1
    assert submitted == InvokeJobBinding(
        run_id="run-1",
        node_id="image-1",
        attempt=2,
        idempotency_key=binding.idempotency_key,
        queue_item_id="41",
        batch_id="batch-7",
        session_id="session-9",
    )
    assert binding.idempotency_key == InvokeJobBinding.create(
        run_id="run-1", node_id="image-1", attempt=2
    ).idempotency_key
    assert binding.idempotency_key != InvokeJobBinding.create(
        run_id="run-1", node_id="image-1", attempt=3
    ).idempotency_key


async def test_reconcile_uses_rest_as_authority_even_when_event_claims_completion():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "GET"
        assert request.url.path == "/api/v1/queue/default/i/41"
        return _response(200, {"item_id": 41, "status": "in_progress", "session_id": "s-1"})

    client = InvokeAIClient(
        InvokeAIConnection("http://invoke.internal:9090"), transport=_transport(handler)
    )
    adapter = InvokeAIAdapter(client)
    binding = InvokeJobBinding.create("run-1", "image-1", 1).with_submission(
        queue_item_id="41", batch_id="b-1", session_id="s-1"
    )

    state = await adapter.reconcile(
        binding,
        event_hint={"event": "queue_item_status_changed", "status": "completed"},
    )

    assert calls == 1
    assert state == InvokeQueueState(
        status="running", raw_status="in_progress", image_names=(), error=None
    )


async def test_completed_reconcile_extracts_only_stable_image_names():
    def handler(request: httpx.Request) -> httpx.Response:
        return _response(
            200,
            {
                "item_id": 41,
                "status": "completed",
                "outputs": [
                    {"image": {"image_name": "out-a.png"}},
                    {"image_name": "out-b.png"},
                    {"url": "http://invoke.internal:9090/api/v1/images/i/private/full"},
                ],
            },
        )

    adapter = InvokeAIAdapter(
        InvokeAIClient(
            InvokeAIConnection("http://invoke.internal:9090"), transport=_transport(handler)
        )
    )
    binding = InvokeJobBinding.create("run-1", "image-1", 1).with_submission(
        queue_item_id="41"
    )

    state = await adapter.reconcile(binding)

    assert state.status == "completed"
    assert state.image_names == ("out-a.png", "out-b.png")
    assert "invoke.internal" not in repr(state)


async def test_cancel_and_image_download_use_fixed_paths_and_stream_bytes():
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "PUT":
            return _response(200, {"item_id": 41, "status": "canceled"})
        return httpx.Response(200, content=b"png-bytes", headers={"content-type": "image/png"})

    client = InvokeAIClient(
        InvokeAIConnection("http://invoke.internal:9090"), transport=_transport(handler)
    )
    await client.cancel_queue_item("41")
    chunks = [chunk async for chunk in client.stream_image("safe-output.png")]

    assert seen == [
        ("PUT", "/api/v1/queue/default/i/41/cancel"),
        ("GET", "/api/v1/images/i/safe-output.png/full"),
    ]
    assert b"".join(chunks) == b"png-bytes"


async def test_model_catalog_uses_only_pinned_read_endpoints():
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path == "/api/v2/models/":
            return _response(200, {"models": [{"key": "m1", "type": "main"}]})
        return _response(200, {"models": []})

    client = InvokeAIClient(
        InvokeAIConnection("http://invoke.internal:9090"), transport=_transport(handler)
    )

    assert await client.list_models() == {"models": [{"key": "m1", "type": "main"}]}
    assert await client.list_missing_models() == {"models": []}
    assert seen == [
        ("GET", "/api/v2/models/"),
        ("GET", "/api/v2/models/missing"),
    ]


@pytest.mark.parametrize("identifier", ["../secret", "a/b", "", "white space"])
async def test_dynamic_path_identifiers_are_rejected_before_network(identifier: str):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("network must not be reached")

    client = InvokeAIClient(
        InvokeAIConnection("http://invoke.internal:9090"), transport=_transport(handler)
    )

    with pytest.raises(ValueError):
        await client.get_queue_item(identifier)


async def test_transport_errors_redact_jwt_authorization_and_response_secrets():
    jwt = "jwt-super-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            request=request,
            text=f"failed Authorization: Bearer {jwt}; token={jwt}",
        )

    client = InvokeAIClient(
        InvokeAIConnection("http://invoke.internal:9090", jwt=jwt),
        transport=_transport(handler),
    )

    with pytest.raises(InvokeAIClientError) as caught:
        await client.get_queue_item("41")

    message = str(caught.value)
    assert jwt not in message
    assert "Bearer" not in message
    assert "***REDACTED***" in message
    assert "invoke.internal" not in message
    assert jwt not in repr(client.connection)


async def test_success_payload_is_recursively_sanitized_before_leaving_client():
    jwt = "jwt-super-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(
            200,
            {
                "item_id": 41,
                "debug": {
                    "authorization": f"Bearer {jwt}",
                    "source": "http://invoke.internal:9090/internal",
                },
            },
        )

    client = InvokeAIClient(
        InvokeAIConnection("http://invoke.internal:9090", jwt=jwt),
        transport=_transport(handler),
    )

    payload = await client.get_queue_item("41")
    serialized = json.dumps(payload)

    assert jwt not in serialized
    assert "Bearer" not in serialized
    assert "invoke.internal" not in serialized


def test_public_results_do_not_serialize_sidecar_connection_material():
    connection = InvokeAIConnection("http://invoke.internal:9090", jwt="jwt-super-secret")
    binding = InvokeJobBinding.create("run-1", "image-1", 1)

    public_payloads = [binding.to_public_dict(), InvokeQueueState("queued", "pending").to_dict()]

    serialized = json.dumps(public_payloads)
    assert "invoke.internal" not in serialized
    assert "jwt-super-secret" not in serialized
    assert "base_url" not in serialized
    assert "jwt" not in serialized
    assert "invoke.internal" not in repr(connection)
