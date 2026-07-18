"""Workflow webhook delivery executor.

Bridges the `intelligence.output.webhook` Canvas node and the
`workflow.notifier.webhook.send` runtime binding to the real
`backend.notifiers.webhook_notifier.WebhookNotifier` (and any other registered
notifier through fanout), while keeping the three preconditions surfaced in
`docs/workflow-node-capability-mapping.md` (EvidenceBatch projection, send
permission, configured webhook URL) as first-class checks rather than
runtime-only implicit assumptions.
"""

from __future__ import annotations

from typing import Any

from backend.notifiers.base import NotificationPayload
from backend.notifiers.registry import get_notifier
from backend.pipeline.notifier_dispatch import _normalize_send_result
from backend.security.url_guard import (
    SSRFValidationError,
    avalidate_public_url,
    validate_public_url,
)

WEBHOOK_DELIVERY_EVENT = "workflow.evidence_batch.ready"
WEBHOOK_DELIVERY_PAYLOAD_SCHEMA = "workflow.webhook.evidence_batch.v1"
WEBHOOK_NOTIFIER_TYPE = "webhook"
WEBHOOK_DELIVERY_REQUIRED_PERMISSION = "canSendNotifications"

EVIDENCE_BATCH_MAX_ITEMS_DEFAULT = 200


class WorkflowWebhookDeliveryError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _resolve_webhook_url_candidate(binding_input: dict[str, Any]) -> str | None:
    config = _read_dict(binding_input.get("config"))
    return (
        _read_string(binding_input.get("url"))
        or _read_string(config.get("url"))
        or _read_string(config.get("webhook_url"))
    )


def resolve_webhook_url(
    binding_input: dict[str, Any],
    *,
    allow_private: bool = False,
) -> str | None:
    """Return the configured webhook URL for a delivery binding or ``None``.

    Performs the SSRF guard validation (scheme + non-private/loopback host)
    before returning, so a caller that just hands the value to the notifier
    is safe against runtime URL smuggling. ``allow_private`` is forwarded
    only when the deployment explicitly opts in (see
    :func:`backend.security.url_guard.is_ip_blocked` for the narrow,
    deliberate use case).

    Sync-only: the SSRF guard performs a blocking DNS lookup, so this helper
    is meant to be called from sync code paths (compile-time node setup, URL
    config validation). Async callers should use
    :func:`resolve_webhook_url_async` or call
    :func:`backend.security.url_guard.avalidate_public_url` directly.
    """

    candidate = _resolve_webhook_url_candidate(binding_input)
    if not candidate:
        return None
    try:
        return validate_public_url(candidate, allow_private=allow_private)
    except SSRFValidationError:
        return None


async def resolve_webhook_url_async(
    binding_input: dict[str, Any],
    *,
    allow_private: bool = False,
) -> str | None:
    """Async-safe equivalent of :func:`resolve_webhook_url` (runs the blocking
    DNS lookup via :func:`backend.security.url_guard.avalidate_public_url`).
    """

    candidate = _resolve_webhook_url_candidate(binding_input)
    if not candidate:
        return None
    try:
        return await avalidate_public_url(candidate, allow_private=allow_private)
    except SSRFValidationError:
        return None


def validate_webhook_url(
    url: str | None,
    *,
    allow_private: bool = False,
) -> str:
    """Validate a webhook URL for the delivery path.

    Returns the normalized URL or raises :class:`SSRFValidationError` (or
    :class:`ValueError` if ``url`` is missing). This is the public hook
    Canvas/tooling uses to verify a configured URL is safe before saving it.
    """

    if not url:
        raise ValueError("Webhook URL is required")
    return validate_public_url(url, allow_private=allow_private)


def project_evidence_batch(
    workflow_id: str,
    run_id: str,
    node_id: str,
    *,
    batch: dict[str, Any] | None = None,
    items: list[dict[str, Any]] | None = None,
    max_items: int = EVIDENCE_BATCH_MAX_ITEMS_DEFAULT,
) -> dict[str, Any]:
    """Project an upstream EvidenceBatch into the webhook delivery payload.

    Accepts either a pre-shaped batch (with optional ``id``/``schema``/custom
    fields) or a raw ``items`` list, and returns the compact payload the
    webhook notifier will post. Empty input is permitted and yields an
    empty-items batch — this is the shape `notifier_dispatch` and the
    Canvas event stream both already understand.

    ``max_items`` caps the projection so a runaway batch can't blow the
    outbound POST past the recipient's body limit; overflow items are
    truncated to ``truncatedItemCount`` rather than silently dropped.
    """

    if batch and isinstance(batch.get("items"), list):
        raw_items = list(batch["items"])
        batch_id = _read_string(batch.get("id")) or f"{run_id}:{node_id}"
        batch_schema = _read_string(batch.get("schema")) or WEBHOOK_DELIVERY_PAYLOAD_SCHEMA
        extras = {k: v for k, v in batch.items() if k not in {"id", "schema", "items"}}
    else:
        raw_items = list(items or [])
        batch_id = f"{run_id}:{node_id}"
        batch_schema = WEBHOOK_DELIVERY_PAYLOAD_SCHEMA
        extras = {}

    truncated = 0
    if max_items and len(raw_items) > max_items:
        truncated = len(raw_items) - max_items
        raw_items = raw_items[:max_items]

    projected_items = [_safe_delivery_item(item) for item in raw_items]
    projection: dict[str, Any] = {
        "id": batch_id,
        "schema": batch_schema,
        "workflowId": workflow_id,
        "workflowRunId": run_id,
        "nodeId": node_id,
        "itemCount": len(projected_items),
        "items": projected_items,
    }
    if truncated:
        projection["truncatedItemCount"] = truncated
    if extras:
        projection["extras"] = extras
    return projection


def assert_send_permission(permissions: list[str] | None) -> None:
    """Raise :class:`WorkflowWebhookDeliveryError` when ``canSendNotifications``
    is not present. Mirrors the runtime IO contract permission_gate.
    """

    granted = {p for p in (permissions or []) if isinstance(p, str)}
    if WEBHOOK_DELIVERY_REQUIRED_PERMISSION not in granted:
        raise WorkflowWebhookDeliveryError(
            code="send_permission_missing",
            message=(
                "Workflow webhook delivery requires the "
                f"{WEBHOOK_DELIVERY_REQUIRED_PERMISSION!r} permission for the "
                "current principal."
            ),
            details={
                "requiredPermission": WEBHOOK_DELIVERY_REQUIRED_PERMISSION,
                "grantedPermissions": sorted(granted),
            },
        )


async def execute_workflow_webhook_delivery(
    binding_input: dict[str, Any],
    input_items: list[dict[str, Any]],
    *,
    workflow_id: str,
    run_id: str,
    node_id: str,
    permissions: list[str] | None = None,
    evidence_batch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = _webhook_config(binding_input)
    target = _read_string(binding_input.get("target")) or "webhook"
    notifier_type = (
        _read_string(binding_input.get("notifierType"))
        or _read_string(config.get("notifierType"))
        or WEBHOOK_NOTIFIER_TYPE
    )
    allow_private = bool(
        binding_input.get("allowPrivateEndpoint") or config.get("allowPrivateEndpoint")
    )

    if notifier_type != WEBHOOK_NOTIFIER_TYPE:
        raise WorkflowWebhookDeliveryError(
            code="notifier_type_unsupported",
            message=(
                "This executor only handles the 'webhook' notifier. Use "
                "execute_workflow_notifier_fanout for multi-notifier dispatch."
            ),
            details={"notifierType": notifier_type, "nodeId": node_id},
        )

    assert_send_permission(permissions)

    webhook_url = resolve_webhook_url(binding_input, allow_private=allow_private)
    if not webhook_url:
        raise WorkflowWebhookDeliveryError(
            code="webhook_url_missing",
            message="Webhook delivery requires a configured webhook URL.",
            details={
                "nodeId": node_id,
                "target": target,
                "payloadSchema": WEBHOOK_DELIVERY_PAYLOAD_SCHEMA,
            },
        )
    config["url"] = webhook_url

    projection = project_evidence_batch(
        workflow_id=workflow_id,
        run_id=run_id,
        node_id=node_id,
        batch=evidence_batch,
        items=input_items,
    )

    payload = NotificationPayload(
        event=WEBHOOK_DELIVERY_EVENT,
        source_id=workflow_id,
        record_id=run_id,
        data={
            **projection,
            "target": target,
        },
    )

    delivered, response_data = _normalize_send_result(
        await get_notifier(WEBHOOK_NOTIFIER_TYPE).send(config, payload)
    )
    if not delivered:
        raise WorkflowWebhookDeliveryError(
            code="webhook_delivery_failed",
            message="Webhook delivery attempted but the notifier returned a failure.",
            details={
                "nodeId": node_id,
                "target": target,
                "itemCount": projection["itemCount"],
                "payloadSchema": WEBHOOK_DELIVERY_PAYLOAD_SCHEMA,
                "responseData": response_data,
            },
        )

    return {
        "notifierType": WEBHOOK_NOTIFIER_TYPE,
        "target": target,
        "deliveryAttempted": True,
        "delivered": True,
        "event": WEBHOOK_DELIVERY_EVENT,
        "payloadSchema": WEBHOOK_DELIVERY_PAYLOAD_SCHEMA,
        "itemCount": projection["itemCount"],
        "batchId": projection["id"],
        "responseData": response_data,
    }


async def execute_workflow_notifier_fanout(
    binding_inputs: list[dict[str, Any]],
    input_items: list[dict[str, Any]],
    *,
    workflow_id: str,
    run_id: str,
    node_id: str,
    permissions: list[str] | None = None,
    evidence_batch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fan a workflow EvidenceBatch out to one or more configured notifier targets.

    Each entry in ``binding_inputs`` is the same shape accepted by
    :func:`execute_workflow_webhook_delivery` (i.e. a node ``params``/``adapter
    config`` object), keyed by ``notifierType`` (defaulting to ``webhook``).
    Failures are collected per notifier; the fanout only raises when *every*
    notifier fails, mirroring the single-notifier behavior callers already
    rely on.
    """

    if not binding_inputs:
        raise WorkflowWebhookDeliveryError(
            code="fanout_empty",
            message="Notifier fanout requires at least one configured target.",
            details={"nodeId": node_id},
        )

    assert_send_permission(permissions)

    projection = project_evidence_batch(
        workflow_id=workflow_id,
        run_id=run_id,
        node_id=node_id,
        batch=evidence_batch,
        items=input_items,
    )

    attempts: list[dict[str, Any]] = []
    any_delivered = False
    for index, binding_input in enumerate(binding_inputs):
        config = _read_dict(binding_input.get("config"))
        notifier_type = (
            _read_string(binding_input.get("notifierType"))
            or _read_string(config.get("notifierType"))
            or WEBHOOK_NOTIFIER_TYPE
        )
        target = (
            _read_string(binding_input.get("target"))
            or _read_string(config.get("target"))
            or notifier_type
        )
        allow_private = bool(
            binding_input.get("allowPrivateEndpoint")
            or config.get("allowPrivateEndpoint")
        )
        attempt: dict[str, Any] = {
            "notifierType": notifier_type,
            "target": target,
            "deliveryAttempted": True,
            "delivered": False,
        }
        try:
            if notifier_type == WEBHOOK_NOTIFIER_TYPE:
                webhook_url = resolve_webhook_url(
                    binding_input, allow_private=allow_private
                )
                if not webhook_url:
                    raise WorkflowWebhookDeliveryError(
                        code="webhook_url_missing",
                        message="Webhook target missing a configured URL.",
                        details={"nodeId": node_id, "fanoutIndex": index},
                    )
                config["url"] = webhook_url
            delivered, response_data = _normalize_send_result(
                await get_notifier(notifier_type).send(
                    config,
                    NotificationPayload(
                        event=WEBHOOK_DELIVERY_EVENT,
                        source_id=workflow_id,
                        record_id=run_id,
                        data={**projection, "target": target},
                    ),
                )
            )
            attempt["delivered"] = bool(delivered)
            attempt["responseData"] = response_data
        except WorkflowWebhookDeliveryError as exc:
            attempt["error"] = {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        except Exception as exc:  # noqa: BLE001 - one bad notifier must not block the others
            attempt["error"] = {
                "code": "notifier_unexpected_error",
                "message": str(exc),
            }

        attempts.append(attempt)
        if attempt["delivered"]:
            any_delivered = True

    if not any_delivered:
        raise WorkflowWebhookDeliveryError(
            code="notifier_fanout_failed",
            message="All configured notifier targets failed to deliver.",
            details={
                "nodeId": node_id,
                "attempts": attempts,
                "itemCount": projection["itemCount"],
            },
        )

    return {
        "notifierType": "fanout",
        "deliveryAttempted": True,
        "delivered": any_delivered,
        "event": WEBHOOK_DELIVERY_EVENT,
        "payloadSchema": WEBHOOK_DELIVERY_PAYLOAD_SCHEMA,
        "itemCount": projection["itemCount"],
        "batchId": projection["id"],
        "attempts": attempts,
    }


def _webhook_config(binding_input: dict[str, Any]) -> dict[str, Any]:
    config = _read_dict(binding_input.get("config"))
    url = (
        _read_string(binding_input.get("url"))
        or _read_string(config.get("url"))
        or _read_string(config.get("webhook_url"))
    )
    if url:
        config = {**config, "url": url}
    return config


def _safe_delivery_item(item: dict[str, Any]) -> dict[str, Any]:
    raw = _read_dict(item.get("raw"))
    normalized = _read_dict(item.get("normalizedData"))
    return {
        "id": _read_string(raw.get("id"))
        or _read_string(normalized.get("id"))
        or _read_string(item.get("recordId")),
        "title": _read_string(raw.get("title")) or _read_string(normalized.get("title")),
        "url": _read_string(raw.get("url")) or _read_string(normalized.get("url")),
        "lineage": _read_dict_list(item.get("lineage")),
    }


def _read_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _read_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


__all__ = [
    "EVIDENCE_BATCH_MAX_ITEMS_DEFAULT",
    "WEBHOOK_DELIVERY_EVENT",
    "WEBHOOK_DELIVERY_PAYLOAD_SCHEMA",
    "WEBHOOK_DELIVERY_REQUIRED_PERMISSION",
    "WEBHOOK_NOTIFIER_TYPE",
    "WorkflowWebhookDeliveryError",
    "assert_send_permission",
    "execute_workflow_notifier_fanout",
    "execute_workflow_webhook_delivery",
    "project_evidence_batch",
    "resolve_webhook_url",
    "resolve_webhook_url_async",
    "validate_webhook_url",
]
