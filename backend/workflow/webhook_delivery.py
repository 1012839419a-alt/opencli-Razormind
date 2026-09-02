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
        payload_data["mode"] = gaojixing["mode"]
        payload_data["provenance"] = gaojixing["provenance"]
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
                    "mode": gaojixing["mode"],
                    "provenance": gaojixing["provenance"],
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
                    "mode": gaojixing["mode"],
                    "provenance": gaojixing["provenance"],
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
        ack = _destination_ack(response_data, gaojixing["deliveryAttemptId"])
        matching_ack = bool(ack and ack["matchesDeliveryAttempt"])
        is_live = gaojixing["mode"] == "live"
        result.update(
            {
                "deliveryAttemptId": gaojixing["deliveryAttemptId"],
                "transportStatus": "accepted",
                "businessOutcome": (
                    "confirmed"
                    if is_live and matching_ack
                    else "unconfirmed"
                    if is_live
                    else gaojixing["mode"]
                ),
                "ackEvidence": ack,
                "packageDigest": gaojixing["packageDigest"],
                "mode": gaojixing["mode"],
                "provenance": gaojixing["provenance"],
                "liveAccepted": is_live and matching_ack,
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
    contexts: list[dict[str, Any]] = []
    for index, item in enumerate(input_items):
        raw = _read_dict(item.get("raw"))
        gaojixing = _read_dict(raw.get("gaojixing"))
        if not gaojixing:
            continue
        package = _read_dict(gaojixing.get("package"))
        evidence = _read_dict(gaojixing.get("evidence"))
        package_digest = _read_string(package.get("digest"))
        mode = _read_string(gaojixing.get("mode"))
        provenance = _read_string(gaojixing.get("provenance"))
        evidence_digest = _read_string(evidence.get("packageDigest"))
        evidence_mode = _read_string(evidence.get("mode"))
        evidence_provenance = _read_string(evidence.get("provenance"))
        context_details = {
            "workflowId": workflow_id,
            "runId": run_id,
            "nodeId": node_id,
            "itemIndex": index,
        }
        if not package_digest or not mode or not provenance:
            raise WorkflowWebhookDeliveryError(
                code="gaojixing_delivery_context_incomplete",
                message="Gaojixing delivery input lacks package, mode, or provenance.",
                details=context_details,
            )
        if (
            evidence_digest != package_digest
            or evidence_mode != mode
            or evidence_provenance != provenance
        ):
            raise WorkflowWebhookDeliveryError(
                code="gaojixing_delivery_evidence_mismatch",
                message="Gaojixing delivery evidence contradicts its source envelope.",
                details={
                    **context_details,
                    "packageDigest": package_digest,
                    "mode": mode,
                    "provenance": provenance,
                },
            )
        _validate_gaojixing_lineage(
            raw=raw,
            gaojixing=gaojixing,
            evidence=evidence,
            source_lineage=_read_dict_list(item.get("lineage")),
            context_details=context_details,
        )
        contexts.append(
            {
                "artifactId": _read_string(gaojixing.get("artifactId")),
                "itemIndex": index,
                "mode": mode,
                "packageDigest": package_digest,
                "provenance": provenance,
                "sourceLineage": _read_dict_list(item.get("lineage")),
            }
        )
    if not contexts:
        return None
    first = contexts[0]
    for context in contexts[1:]:
        inconsistent = [
            field
            for field in ("packageDigest", "mode", "provenance")
            if context[field] != first[field]
        ]
        if inconsistent:
            raise WorkflowWebhookDeliveryError(
                code="gaojixing_delivery_context_mismatch",
                message="Gaojixing delivery batch mixes incompatible source contexts.",
                details={
                    "workflowId": workflow_id,
                    "runId": run_id,
                    "nodeId": node_id,
                    "itemIndex": context["itemIndex"],
                    "inconsistentFields": inconsistent,
                },
            )
    lineage = {
        "workflowId": workflow_id,
        "workflowRunId": run_id,
        "nodeId": node_id,
        "packageDigest": first["packageDigest"],
        "artifactId": first["artifactId"],
        "sourceLineage": first["sourceLineage"],
        "mode": first["mode"],
        "provenance": first["provenance"],
    }
    delivery_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            (
                "opencli-admin/gaojixing/delivery/"
                f"{workflow_id}/{run_id}/{node_id}/{first['packageDigest']}"
            ),
        )
    )
    return {
        "deliveryAttemptId": delivery_id,
        "packageDigest": first["packageDigest"],
        "lineage": lineage,
        "mode": first["mode"],
        "provenance": first["provenance"],
    }


def _destination_ack(
    response_data: dict[str, Any] | None, delivery_attempt_id: str
) -> dict[str, Any] | None:
    if not isinstance(response_data, dict):
        return None
    confirmation_field: str | None = None
    for key in ("businessAck", "business_ack", "acknowledged"):
        if response_data.get(key) is True:
            confirmation_field = key
            break
    status = _read_string(response_data.get("status"))
    if confirmation_field is None and status in {"confirmed", "acknowledged"}:
        confirmation_field = "status"
    if confirmation_field is None:
        return None
    ack_delivery_id = _delivery_attempt_id(response_data)
    return {
        "status": "confirmed",
        "source": "destination_response",
        "field": confirmation_field,
        "deliveryAttemptId": ack_delivery_id,
        "matchesDeliveryAttempt": ack_delivery_id == delivery_attempt_id,
    }


def _validate_gaojixing_lineage(
    *,
    raw: dict[str, Any],
    gaojixing: dict[str, Any],
    evidence: dict[str, Any],
    source_lineage: list[dict[str, Any]],
    context_details: dict[str, Any],
) -> None:
    package = _read_dict(gaojixing.get("package"))
    package_digest = _read_string(package.get("digest"))
    artifact_id = _read_string(gaojixing.get("artifactId"))
    expected = {
        "packageDigest": package_digest,
        "artifactId": artifact_id,
        "mode": _read_string(gaojixing.get("mode")),
        "provenance": _read_string(gaojixing.get("provenance")),
        "runId": _read_string(evidence.get("runId")),
        "workflowId": _read_string(evidence.get("workflowId")),
        "nodeId": _read_string(evidence.get("nodeId")),
    }
    raw_digest = _read_string(raw.get("packageDigest"))
    question_package = _read_dict(raw.get("questionPackage"))
    mismatches = [
        field
        for field, actual, expected_value in (
            ("packageDigest", raw_digest, package_digest),
            (
                "questionPackage.digest",
                _read_string(question_package.get("digest")),
                package_digest,
            ),
            (
                "evidence.answer.artifactId",
                _read_string(_read_dict(evidence.get("answer")).get("artifactId")),
                artifact_id,
            ),
        )
        if actual is not None and actual != expected_value
    ]
    for entry in source_lineage:
        for field, expected_value in expected.items():
            actual = _read_string(entry.get(field))
            if field == "mode" and actual == "persisted-replay":
                continue
            if actual is not None and expected_value is not None and actual != expected_value:
                mismatches.append(f"sourceLineage.{field}")
    if mismatches:
        raise WorkflowWebhookDeliveryError(
            code="gaojixing_delivery_lineage_mismatch",
            message="Gaojixing delivery lineage contradicts its immutable source evidence.",
            details={**context_details, "mismatchedFields": sorted(set(mismatches))},
        )


def _delivery_attempt_id(response_data: dict[str, Any]) -> str | None:
    keys = (
        "deliveryAttemptId",
        "delivery_attempt_id",
        "deliveryId",
        "delivery_id",
        "idempotencyKey",
    )
    for key in keys:
        value = _read_string(response_data.get(key))
        if value:
            return value
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
