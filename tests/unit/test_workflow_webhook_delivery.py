"""Unit tests for the workflow webhook delivery executor.

Covers the three preconditions documented in
`docs/workflow-node-capability-mapping.md` (EvidenceBatch projection, send
permission, configured webhook URL) and the multi-notifier fanout path that
lands alongside the single-webhook executor.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.notifiers.base import (
    AbstractNotifier,
    NotificationPayload,
    NotificationSendResult,
)
from backend.notifiers.registry import get_notifier
from backend.workflow.webhook_delivery import (
    EVIDENCE_BATCH_MAX_ITEMS_DEFAULT,
    WEBHOOK_DELIVERY_EVENT,
    WEBHOOK_DELIVERY_PAYLOAD_SCHEMA,
    WEBHOOK_NOTIFIER_TYPE,
    WorkflowWebhookDeliveryError,
    assert_send_permission,
    execute_workflow_notifier_fanout,
    execute_workflow_webhook_delivery,
    project_evidence_batch,
    resolve_webhook_url,
    resolve_webhook_url_async,
    validate_webhook_url,
)


# ── projection ──────────────────────────────────────────────────────────────


def test_project_evidence_batch_from_items() -> None:
    projection = project_evidence_batch(
        workflow_id="wf-1",
        run_id="run-1",
        node_id="notify-webhook",
        items=[
            {
                "raw": {
                    "id": "r1",
                    "title": "first",
                    "url": "https://httpbin.org/r1",
                },
                "lineage": [{"source": "opencli"}],
            },
            {
                "normalizedData": {
                    "id": "r2",
                    "title": "second",
                    "url": "https://httpbin.org/r2",
                },
                "lineage": [{"source": "api"}],
            },
        ],
    )

    assert projection["schema"] == WEBHOOK_DELIVERY_PAYLOAD_SCHEMA
    assert projection["workflowId"] == "wf-1"
    assert projection["workflowRunId"] == "run-1"
    assert projection["nodeId"] == "notify-webhook"
    assert projection["itemCount"] == 2
    assert projection["id"] == "run-1:notify-webhook"
    assert projection["items"][0]["id"] == "r1"
    assert projection["items"][0]["title"] == "first"
    assert projection["items"][0]["url"] == "https://httpbin.org/r1"
    assert projection["items"][0]["lineage"] == [{"source": "opencli"}]
    assert projection["items"][1]["id"] == "r2"
    assert "truncatedItemCount" not in projection


def test_project_evidence_batch_from_pre_shaped_batch() -> None:
    projection = project_evidence_batch(
        workflow_id="wf-1",
        run_id="run-1",
        node_id="notify-webhook",
        batch={
            "id": "external-batch-7",
            "schema": "evidence.batch.external.v1",
            "items": [{"raw": {"id": "x1", "title": "x"}}],
            "sourceRunId": "src-1",
        },
    )

    assert projection["id"] == "external-batch-7"
    assert projection["schema"] == "evidence.batch.external.v1"
    assert projection["itemCount"] == 1
    assert projection["extras"] == {"sourceRunId": "src-1"}


def test_project_evidence_batch_truncates_overflow() -> None:
    items = [{"raw": {"id": f"id-{i}"}} for i in range(EVIDENCE_BATCH_MAX_ITEMS_DEFAULT + 5)]
    projection = project_evidence_batch(
        workflow_id="wf-1",
        run_id="run-1",
        node_id="notify-webhook",
        items=items,
    )

    assert projection["itemCount"] == EVIDENCE_BATCH_MAX_ITEMS_DEFAULT
    assert projection["truncatedItemCount"] == 5
    assert len(projection["items"]) == EVIDENCE_BATCH_MAX_ITEMS_DEFAULT


def test_project_evidence_batch_empty_items() -> None:
    projection = project_evidence_batch(
        workflow_id="wf-1",
        run_id="run-1",
        node_id="notify-webhook",
        items=[],
    )
    assert projection["itemCount"] == 0
    assert projection["items"] == []
    assert "truncatedItemCount" not in projection


# ── URL validation ──────────────────────────────────────────────────────────


def test_resolve_webhook_url_returns_normalized_when_safe() -> None:
    url = resolve_webhook_url(
        {"url": "https://httpbin.org/opencli-admin-backend"}
    )
    assert url == "https://httpbin.org/opencli-admin-backend"


def test_resolve_webhook_url_prefers_config_url() -> None:
    url = resolve_webhook_url(
        {
            "url": "https://httpbin.org/primary",
            "config": {"url": "https://httpbin.org/fallback"},
        }
    )
    assert url == "https://httpbin.org/primary"


def test_resolve_webhook_url_returns_none_for_blocked_host() -> None:
    """Loopback/private addresses must be rejected by the SSRF guard."""
    assert resolve_webhook_url({"url": "http://127.0.0.1:8080/hook"}) is None
    assert resolve_webhook_url({"url": "http://localhost:8080/hook"}) is None
    assert resolve_webhook_url({"url": "http://10.0.0.5/hook"}) is None
    assert (
        resolve_webhook_url({"url": "ftp://httpbin.org/hook"}) is None
    )  # wrong scheme


def test_resolve_webhook_url_returns_none_when_unconfigured() -> None:
    assert resolve_webhook_url({}) is None
    assert resolve_webhook_url({"config": {}}) is None
    assert resolve_webhook_url({"url": ""}) is None
    assert resolve_webhook_url({"url": "  "}) is None


def test_validate_webhook_url_normalizes_safe_url() -> None:
    assert (
        validate_webhook_url("https://httpbin.org/x")
        == "https://httpbin.org/x"
    )


def test_validate_webhook_url_rejects_empty() -> None:
    with pytest.raises(ValueError):
        validate_webhook_url(None)
    with pytest.raises(ValueError):
        validate_webhook_url("")


def test_validate_webhook_url_rejects_loopback() -> None:
    from backend.security.url_guard import SSRFValidationError

    with pytest.raises(SSRFValidationError):
        validate_webhook_url("http://127.0.0.1/x")


@pytest.mark.asyncio
async def test_resolve_webhook_url_async_uses_async_guard() -> None:
    url = await resolve_webhook_url_async(
        {"url": "https://httpbin.org/async"}
    )
    assert url == "https://httpbin.org/async"


# ── permission gate ─────────────────────────────────────────────────────────


def test_assert_send_permission_accepts_granted() -> None:
    assert_send_permission(["canSendNotifications", "canFetchNetwork"])


def test_assert_send_permission_rejects_when_missing() -> None:
    with pytest.raises(WorkflowWebhookDeliveryError) as exc_info:
        assert_send_permission(["canFetchNetwork"])

    assert exc_info.value.code == "send_permission_missing"
    assert exc_info.value.details["requiredPermission"] == "canSendNotifications"
    assert "canFetchNetwork" in exc_info.value.details["grantedPermissions"]


def test_assert_send_permission_tolerates_none_or_empty() -> None:
    with pytest.raises(WorkflowWebhookDeliveryError):
        assert_send_permission(None)
    with pytest.raises(WorkflowWebhookDeliveryError):
        assert_send_permission([])


# ── single-target delivery ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_webhook_delivery_succeeds_with_full_preconditions() -> None:
    captured: dict[str, Any] = {}

    async def fake_guarded_async_client(url, **client_kwargs):
        async def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            captured["headers"] = dict(request.headers)
            return httpx.Response(200, request=request)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler)), url

    with patch(
        "backend.notifiers.webhook_notifier.guarded_async_client",
        fake_guarded_async_client,
    ):
        result = await execute_workflow_webhook_delivery(
            {
                "target": "test-webhook",
                "url": "https://httpbin.org/opencli-admin-backend",
                "config": {"secret": "shh", "timeout": 5},
            },
            [
                {
                    "raw": {
                        "id": "r1",
                        "title": "first",
                        "url": "https://httpbin.org/r1",
                    },
                    "lineage": [{"source": "opencli"}],
                }
            ],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-webhook",
            permissions=["canSendNotifications"],
        )

    assert result["notifierType"] == "webhook"
    assert result["target"] == "test-webhook"
    assert result["delivered"] is True
    assert result["event"] == WEBHOOK_DELIVERY_EVENT
    assert result["payloadSchema"] == WEBHOOK_DELIVERY_PAYLOAD_SCHEMA
    assert result["itemCount"] == 1
    assert result["batchId"] == "run-1:notify-webhook"
    assert result["responseData"]["status_code"] == 200

    body = captured["body"]
    assert body["event"] == WEBHOOK_DELIVERY_EVENT
    assert body["source_id"] == "wf-1"
    assert body["record_id"] == "run-1"
    assert body["data"]["schema"] == WEBHOOK_DELIVERY_PAYLOAD_SCHEMA
    assert body["data"]["itemCount"] == 1
    assert body["data"]["items"][0]["id"] == "r1"
    expected_sig = hmac.new(
        b"shh",
        json.dumps(body).encode(),
        hashlib.sha256,
    ).hexdigest()
    assert captured["headers"]["x-signature-256"] == f"sha256={expected_sig}"


@pytest.mark.asyncio
async def test_execute_webhook_delivery_uses_pre_shaped_evidence_batch() -> None:
    captured: dict[str, Any] = {}

    async def fake_guarded_async_client(url, **client_kwargs):
        async def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, request=request)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler)), url

    with patch(
        "backend.notifiers.webhook_notifier.guarded_async_client",
        fake_guarded_async_client,
    ):
        result = await execute_workflow_webhook_delivery(
            {
                "url": "https://httpbin.org/opencli-admin-backend",
            },
            [],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-webhook",
            permissions=["canSendNotifications"],
            evidence_batch={
                "id": "evidence-batch-42",
                "schema": "evidence.batch.external.v1",
                "items": [
                    {
                        "raw": {
                            "id": "x1",
                            "title": "from-upstream",
                            "url": "https://httpbin.org/x1",
                        }
                    }
                ],
            },
        )

    assert result["batchId"] == "evidence-batch-42"
    assert result["itemCount"] == 1
    assert captured["body"]["data"]["schema"] == "evidence.batch.external.v1"
    assert captured["body"]["data"]["items"][0]["id"] == "x1"


@pytest.mark.asyncio
async def test_execute_webhook_delivery_blocks_without_send_permission() -> None:
    with pytest.raises(WorkflowWebhookDeliveryError) as exc_info:
        await execute_workflow_webhook_delivery(
            {"url": "https://httpbin.org/x"},
            [{"raw": {"id": "r1"}}],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-webhook",
            permissions=[],
        )
    assert exc_info.value.code == "send_permission_missing"


@pytest.mark.asyncio
async def test_execute_webhook_delivery_blocks_without_url() -> None:
    with pytest.raises(WorkflowWebhookDeliveryError) as exc_info:
        await execute_workflow_webhook_delivery(
            {"target": "no-url"},
            [],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-webhook",
            permissions=["canSendNotifications"],
        )
    assert exc_info.value.code == "webhook_url_missing"


@pytest.mark.asyncio
async def test_execute_webhook_delivery_blocks_on_loopback_url() -> None:
    with pytest.raises(WorkflowWebhookDeliveryError) as exc_info:
        await execute_workflow_webhook_delivery(
            {"url": "http://127.0.0.1:9999/hook"},
            [],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-webhook",
            permissions=["canSendNotifications"],
        )
    assert exc_info.value.code == "webhook_url_missing"


@pytest.mark.asyncio
async def test_execute_webhook_delivery_raises_on_notifier_failure() -> None:
    async def fake_guarded_async_client(url, **client_kwargs):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, request=request)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler)), url

    with patch(
        "backend.notifiers.webhook_notifier.guarded_async_client",
        fake_guarded_async_client,
    ):
        with pytest.raises(WorkflowWebhookDeliveryError) as exc_info:
            await execute_workflow_webhook_delivery(
                {"url": "https://httpbin.org/x"},
                [{"raw": {"id": "r1"}}],
                workflow_id="wf-1",
                run_id="run-1",
                node_id="notify-webhook",
                permissions=["canSendNotifications"],
            )
    assert exc_info.value.code == "webhook_delivery_failed"
    assert exc_info.value.details["responseData"]["status_code"] == 500


@pytest.mark.asyncio
async def test_execute_webhook_delivery_rejects_non_webhook_notifier_type() -> None:
    with pytest.raises(WorkflowWebhookDeliveryError) as exc_info:
        await execute_workflow_webhook_delivery(
            {
                "url": "https://httpbin.org/x",
                "notifierType": "feishu",
            },
            [],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-webhook",
            permissions=["canSendNotifications"],
        )
    assert exc_info.value.code == "notifier_type_unsupported"


# ── fanout ──────────────────────────────────────────────────────────────────


class _RecordingFeishuNotifier(AbstractNotifier):
    notifier_type = "feishu"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send(
        self,
        config: dict[str, Any],
        payload: NotificationPayload,
    ) -> NotificationSendResult:
        self.calls.append(
            {"config": dict(config), "event": payload.event, "data": dict(payload.data)}
        )
        return NotificationSendResult(success=True, response_data={"status_code": 200})


class _FailingDingTalkNotifier(AbstractNotifier):
    notifier_type = "dingtalk"

    async def send(
        self,
        config: dict[str, Any],
        payload: NotificationPayload,
    ) -> bool:
        return False


@pytest.mark.asyncio
async def test_execute_workflow_notifier_fanout_delivers_to_multiple_targets() -> None:
    feishu = _RecordingFeishuNotifier()

    async def fake_guarded_async_client(url, **client_kwargs):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, request=request)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler)), url

    with (
        patch("backend.notifiers.webhook_notifier.guarded_async_client", fake_guarded_async_client),
        patch("backend.workflow.webhook_delivery.get_notifier") as mock_get,
    ):
        mock_get.side_effect = (
            lambda notifier_type: feishu
            if notifier_type == "feishu"
            else get_notifier(notifier_type)
        )

        result = await execute_workflow_notifier_fanout(
            [
                {
                    "target": "feishu-bot",
                    "notifierType": "feishu",
                    "config": {"webhook_url": "https://open.feishu.cn/hook/x"},
                },
                {
                    "target": "generic-webhook",
                    "notifierType": "webhook",
                    "url": "https://httpbin.org/x",
                },
            ],
            [{"raw": {"id": "r1", "title": "fanned out"}}],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-fanout",
            permissions=["canSendNotifications"],
        )

    assert result["notifierType"] == "fanout"
    assert result["delivered"] is True
    assert result["itemCount"] == 1
    assert len(result["attempts"]) == 2
    assert all(attempt["delivered"] is True for attempt in result["attempts"])
    assert feishu.calls and feishu.calls[0]["event"] == WEBHOOK_DELIVERY_EVENT


@pytest.mark.asyncio
async def test_execute_workflow_notifier_fanout_raises_when_all_fail() -> None:
    async def fake_guarded_async_client(url, **client_kwargs):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, request=request)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler)), url

    with (
        patch("backend.notifiers.webhook_notifier.guarded_async_client", fake_guarded_async_client),
        patch(
            "backend.workflow.webhook_delivery.get_notifier",
            side_effect=lambda nt: _FailingDingTalkNotifier() if nt == "dingtalk" else get_notifier(nt),
        ),
    ):
        with pytest.raises(WorkflowWebhookDeliveryError) as exc_info:
            await execute_workflow_notifier_fanout(
                [
                    {
                        "notifierType": "webhook",
                        "url": "https://httpbin.org/x",
                    },
                    {
                        "notifierType": "dingtalk",
                        "config": {"webhook_url": "https://oapi.dingtalk.com/robot/x"},
                    },
                ],
                [{"raw": {"id": "r1"}}],
                workflow_id="wf-1",
                run_id="run-1",
                node_id="notify-fanout",
                permissions=["canSendNotifications"],
            )

    assert exc_info.value.code == "notifier_fanout_failed"
    assert len(exc_info.value.details["attempts"]) == 2
    statuses = [a["delivered"] for a in exc_info.value.details["attempts"]]
    assert statuses == [False, False]


@pytest.mark.asyncio
async def test_execute_workflow_notifier_fanout_succeeds_when_at_least_one_delivers() -> None:
    async def fake_guarded_async_client(url, **client_kwargs):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, request=request)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler)), url

    with (
        patch("backend.notifiers.webhook_notifier.guarded_async_client", fake_guarded_async_client),
        patch(
            "backend.workflow.webhook_delivery.get_notifier",
            side_effect=lambda nt: _FailingDingTalkNotifier() if nt == "dingtalk" else get_notifier(nt),
        ),
    ):
        result = await execute_workflow_notifier_fanout(
            [
                {
                    "notifierType": "dingtalk",
                    "config": {"webhook_url": "https://oapi.dingtalk.com/robot/x"},
                },
                {
                    "notifierType": "webhook",
                    "url": "https://httpbin.org/x",
                },
            ],
            [{"raw": {"id": "r1"}}],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-fanout",
            permissions=["canSendNotifications"],
        )

    assert result["delivered"] is True
    delivered_attempts = [a for a in result["attempts"] if a["delivered"]]
    failed_attempts = [a for a in result["attempts"] if not a["delivered"]]
    assert len(delivered_attempts) == 1
    assert delivered_attempts[0]["notifierType"] == "webhook"
    assert len(failed_attempts) == 1
    assert failed_attempts[0]["notifierType"] == "dingtalk"


@pytest.mark.asyncio
async def test_execute_workflow_notifier_fanout_blocks_without_permission() -> None:
    with pytest.raises(WorkflowWebhookDeliveryError) as exc_info:
        await execute_workflow_notifier_fanout(
            [
                {
                    "notifierType": "webhook",
                    "url": "https://httpbin.org/x",
                }
            ],
            [],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-fanout",
            permissions=["canFetchNetwork"],
        )
    assert exc_info.value.code == "send_permission_missing"


@pytest.mark.asyncio
async def test_execute_workflow_notifier_fanout_blocks_when_empty() -> None:
    with pytest.raises(WorkflowWebhookDeliveryError) as exc_info:
        await execute_workflow_notifier_fanout(
            [],
            [],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-fanout",
            permissions=["canSendNotifications"],
        )
    assert exc_info.value.code == "fanout_empty"


@pytest.mark.asyncio
async def test_execute_workflow_notifier_fanout_swallows_unexpected_errors() -> None:
    class _ExplodingNotifier(AbstractNotifier):
        notifier_type = "wecom"

        async def send(
            self,
            config: dict[str, Any],
            payload: NotificationPayload,
        ) -> bool:
            raise RuntimeError("boom")

    async def fake_guarded_async_client(url, **client_kwargs):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, request=request)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler)), url

    with (
        patch("backend.notifiers.webhook_notifier.guarded_async_client", fake_guarded_async_client),
        patch(
            "backend.workflow.webhook_delivery.get_notifier",
            side_effect=lambda nt: _ExplodingNotifier() if nt == "wecom" else get_notifier(nt),
        ),
    ):
        result = await execute_workflow_notifier_fanout(
            [
                {
                    "notifierType": "wecom",
                    "config": {"webhook_url": "https://qyapi.weixin.qq.com/hook"},
                },
                {
                    "notifierType": "webhook",
                    "url": "https://httpbin.org/x",
                },
            ],
            [{"raw": {"id": "r1"}}],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-fanout",
            permissions=["canSendNotifications"],
        )

    assert result["delivered"] is True
    wecom_attempt = next(
        attempt for attempt in result["attempts"] if attempt["notifierType"] == "wecom"
    )
    assert wecom_attempt["delivered"] is False
    assert wecom_attempt["error"]["code"] == "notifier_unexpected_error"


# ── capability projection ───────────────────────────────────────────────────


def test_capability_projection_webhook_catalog_lists_real_executor() -> None:
    from backend.workflow import capability_projection

    catalog = {
        item.id: item
        for item in capability_projection._catalog_base_capabilities()
    }
    node = catalog["intelligence.output.webhook"]
    assert node.status == "blocked"
    assert node.runtimeBinding == "workflow.notifier.webhook.send"
    assert node.source == "backend.workflow.webhook_delivery"
    manifest = node.manifest
    assert manifest["permissions"] == ["canSendNotifications"]
    contract = manifest["contract"]
    assert contract["inputShape"]["ports"][0] == {"name": "in", "type": "EvidenceBatch"}
    assert contract["outputShape"]["ports"][0] == {
        "name": "delivery",
        "type": "webhookDeliveryAttempt",
    }
    assert "blocked:webhook_url_missing" in manifest["trace"]["events"]
    assert "webhook_url_validated" in manifest["probes"]


def test_capability_projection_webhook_notifier_is_runnable() -> None:
    from backend.workflow import capability_projection

    notifiers = {
        item.notifierType: item
        for item in capability_projection._notifier_capabilities()
    }
    webhook_notifier = notifiers["webhook"]
    assert webhook_notifier.status == "runnable"
    assert webhook_notifier.missing == []
    assert webhook_notifier.runtimeBinding == "workflow.notifier.webhook.send"


def test_capability_projection_dispatch_fanout_is_runnable() -> None:
    from backend.workflow import capability_projection

    catalog = {
        item.id: item
        for item in capability_projection._catalog_base_capabilities()
    }
    fanout = catalog["package.dispatch.fanout"]
    assert fanout.status == "runnable"
    assert fanout.source == "backend.workflow.webhook_delivery"
    # The catalog declares blocked:fanout_empty in its own trace events (the
    # contract-level eventShape only covers the webhook notifier events).
    assert "blocked:fanout_empty" in fanout.manifest["trace"]["events"]


# ── integration with the real webhook notifier ─────────────────────────────


@pytest.mark.asyncio
async def test_real_webhook_notifier_uses_guarded_client() -> None:
    """Smoke-check the real WebhookNotifier still composes with our delivery
    executor; patches guarded_async_client so no network is involved."""
    captured: dict[str, Any] = {}

    async def fake_guarded_async_client(url, **client_kwargs):
        async def handler(request: httpx.Request) -> httpx.Response:
            captured["called"] = True
            return httpx.Response(200, request=request)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler)), url

    with patch(
        "backend.notifiers.webhook_notifier.guarded_async_client",
        fake_guarded_async_client,
    ):
        result = await execute_workflow_webhook_delivery(
            {
                "url": "https://httpbin.org/real-notifier",
                "config": {},
            },
            [{"raw": {"id": "r1", "title": "t"}}],
            workflow_id="wf-1",
            run_id="run-1",
            node_id="notify-webhook",
            permissions=["canSendNotifications"],
        )

    assert captured.get("called") is True
    assert result["delivered"] is True
    assert result["notifierType"] == WEBHOOK_NOTIFIER_TYPE
