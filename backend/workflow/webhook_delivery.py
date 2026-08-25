"""Workflow webhook delivery executor."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from backend.notifiers.base import NotificationPayload
from backend.notifiers.registry import get_notifier
from backend.pipeline.notifier_dispatch import _normalize_send_result

WEBHOOK_DELIVERY_EVENT = "workflow.evidence_batch.ready"
WEBHOOK_DELIVERY_PAYLOAD_SCHEMA = "workflow.webhook.evidence_batch.v1"


class WorkflowWebhookDeliveryError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


async def execute_workflow_webhook_delivery(
    binding_input: dict[str, Any],
    input_items: list[dict[str, Any]],
    *,
    workflow_id: str,
    run_id: str,
    node_id: str,
) -> dict[str, Any]:
    config = _webhook_config(binding_input)
    target = _read_string(binding_input.get("target")) or "webhook"
    gaojixing = _gaojixing_delivery_context(
        input_items,
        workflow_id=workflow_id,
        run_id=run_id,
        node_id=node_id,
    )
    payload_data = {
        "schema": WEBHOOK_DELIVERY_PAYLOAD_SCHEMA,
        "workflowId": workflow_id,
        "workflowRunId": run_id,
        "nodeId": node_id,
        "target": target,
        "itemCount": len(input_items),
        "items": [_safe_delivery_item(item) for item in input_items],
    }
    if gaojixing:
        payload_data["packageDigest"] = gaojixing["packageDigest"]
        payload_data["lineage"] = gaojixing["lineage"]
    payload = NotificationPayload(
        event=WEBHOOK_DELIVERY_EVENT,
        source_id=workflow_id,
        delivery_id=gaojixing["deliveryAttemptId"] if gaojixing else None,
        record_id=run_id,
        data=payload_data,
        lineage=gaojixing["lineage"] if gaojixing else None,
    )

    try:
        delivered, response_data = _normalize_send_result(
            await get_notifier("webhook").send(config, payload)
        )
    except WorkflowWebhookDeliveryError:
        raise
    except (httpx.HTTPError, OSError) as exc:
        details = {
            "nodeId": node_id,
            "target": target,
            "itemCount": len(input_items),
            "payloadSchema": WEBHOOK_DELIVERY_PAYLOAD_SCHEMA,
        }
        if gaojixing:
            details.update(
                {
                    "deliveryAttemptId": gaojixing["deliveryAttemptId"],
                    "transportStatus": "failed",
                    "businessOutcome": "unknown",
                    "lineage": gaojixing["lineage"],
                }
            )
        raise WorkflowWebhookDeliveryError(
            code="webhook_delivery_network_error",
            message=f"Webhook delivery failed due to a network error: {exc}",
            details=details,
        ) from exc
    if not delivered:
        details = {
            "nodeId": node_id,
            "target": target,
            "itemCount": len(input_items),
            "payloadSchema": WEBHOOK_DELIVERY_PAYLOAD_SCHEMA,
        }
        if gaojixing:
            details.update(
                {
                    "deliveryAttemptId": gaojixing["deliveryAttemptId"],
                    "transportStatus": "failed",
                    "businessOutcome": "unknown",
                    "lineage": gaojixing["lineage"],
                }
            )
        raise WorkflowWebhookDeliveryError(
            code="webhook_delivery_failed",
            message="Webhook delivery attempted but the notifier returned a failure.",
            details=details,
        )

    result = {
        "notifierType": "webhook",
        "target": target,
        "deliveryAttempted": True,
        "delivered": True,
        "event": WEBHOOK_DELIVERY_EVENT,
        "payloadSchema": WEBHOOK_DELIVERY_PAYLOAD_SCHEMA,
        "itemCount": len(input_items),
    }
    if gaojixing:
        ack = _destination_ack(response_data)
        result.update(
            {
                "deliveryAttemptId": gaojixing["deliveryAttemptId"],
                "transportStatus": "accepted",
                "businessOutcome": "confirmed" if ack else "unconfirmed",
                "ackEvidence": ack,
                "packageDigest": gaojixing["packageDigest"],
                "lineage": gaojixing["lineage"],
            }
        )
    return result

def _gaojixing_delivery_context(
    input_items: list[dict[str, Any]],
    *,
    workflow_id: str,
    run_id: str,
    node_id: str,
) -> dict[str, Any] | None:
    for item in input_items:
        raw = _read_dict(item.get("raw"))
        gaojixing = _read_dict(raw.get("gaojixing"))
        if not gaojixing:
            continue
        package = _read_dict(gaojixing.get("package"))
        package_digest = _read_string(package.get("digest"))
        if not package_digest:
            continue
        lineage = {
            "workflowId": workflow_id,
            "workflowRunId": run_id,
            "nodeId": node_id,
            "packageDigest": package_digest,
            "artifactId": _read_string(gaojixing.get("artifactId")),
            "sourceLineage": _read_dict_list(item.get("lineage")),
        }
        delivery_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"opencli-admin/gaojixing/delivery/{workflow_id}/{run_id}/{node_id}/{package_digest}",
            )
        )
        return {
            "deliveryAttemptId": delivery_id,
            "packageDigest": package_digest,
            "lineage": lineage,
        }
    return None


def _destination_ack(response_data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(response_data, dict):
        return None
    for key in ("businessAck", "business_ack", "acknowledged"):
        if response_data.get(key) is True:
            return {"status": "confirmed", "source": "destination_response", "field": key}
    status = _read_string(response_data.get("status"))
    if status in {"confirmed", "acknowledged"}:
        return {"status": "confirmed", "source": "destination_response", "field": "status"}
    return None


def _webhook_config(binding_input: dict[str, Any]) -> dict[str, Any]:
    config = _read_dict(binding_input.get("config"))
    url = _read_string(binding_input.get("url")) or _read_string(
        config.get("url")
    ) or _read_string(config.get("webhook_url"))
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
    "WEBHOOK_DELIVERY_EVENT",
    "WEBHOOK_DELIVERY_PAYLOAD_SCHEMA",
    "WorkflowWebhookDeliveryError",
    "execute_workflow_webhook_delivery",
]
