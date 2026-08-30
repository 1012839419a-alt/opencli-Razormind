"""Execution of one frozen delivery authorization through receiver v2."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.delivery_authorization import DeliveryAuthorizationDecisionV1, DeliveryTargetRevision
from backend.models.delivery_execution import DeliveryExecution, DeliveryExecutionResult
from backend.schemas.delivery_execution import DeliveryExecutionListV1, DeliveryExecutionReadV1
from backend.security.controlled_receiver import (
    ControlledReceiverSecurityError,
    canonical_hash,
    canonical_json,
    pinned_post,
    request_headers,
    resolve_endpoint,
    verify_receipt,
)
from backend.workflow.delivery_authorization import DeliveryAuthorizationScope


class DeliveryExecutionConflictError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _payload(decision: DeliveryAuthorizationDecisionV1) -> dict[str, Any]:
    try:
        projection = {
            "schemaVersion": decision.payload_schema_version,
            "claims": decision.selected_claims,
            "manifestHashes": [item["manifestHash"] for item in decision.manifest_set],
        }
    except (KeyError, TypeError) as exc:
        raise DeliveryExecutionConflictError("Frozen authorization payload cannot be reconstructed") from exc
    if canonical_hash(projection) != decision.payload_hash:
        raise DeliveryExecutionConflictError("Frozen authorization payload hash mismatch")
    return projection


def _binding(decision: DeliveryAuthorizationDecisionV1) -> str:
    return canonical_hash({
        "decisionId": decision.id,
        "decisionHash": decision.decision_hash,
        "targetRevisionId": decision.target_revision_id,
        "targetRevision": decision.target_revision,
        "payloadHash": decision.payload_hash,
        "policyVersion": decision.policy_version,
        "policyHash": decision.policy_hash,
    })


def _read(execution: DeliveryExecution, results: list[DeliveryExecutionResult]) -> DeliveryExecutionReadV1:
    return DeliveryExecutionReadV1(
        execution_id=execution.id,
        decision_id=execution.decision_id,
        operation_id=execution.operation_id,
        decision_hash=execution.decision_hash,
        payload_hash=execution.payload_hash,
        state=execution.state,
        outcome=execution.final_outcome,
        attempt_count=len(results),
        created_at=execution.created_at,
        updated_at=execution.updated_at,
    )


async def _results(db: AsyncSession, execution_id: str) -> list[DeliveryExecutionResult]:
    return list((await db.execute(select(DeliveryExecutionResult).where(DeliveryExecutionResult.execution_id == execution_id).order_by(DeliveryExecutionResult.attempt_number))).scalars())


async def _scoped_decision(db: AsyncSession, scope: DeliveryAuthorizationScope, decision_id: str) -> DeliveryAuthorizationDecisionV1:
    decision = await db.scalar(select(DeliveryAuthorizationDecisionV1).where(
        DeliveryAuthorizationDecisionV1.id == decision_id,
        DeliveryAuthorizationDecisionV1.workspace_id == scope.workspace_id,
        DeliveryAuthorizationDecisionV1.project_id == scope.project_id,
        DeliveryAuthorizationDecisionV1.workflow_id == scope.workflow_id,
        DeliveryAuthorizationDecisionV1.studio_workflow_version_id == scope.studio_workflow_version_id,
        DeliveryAuthorizationDecisionV1.run_id == scope.run_id,
    ).with_for_update())
    if decision is None:
        raise DeliveryExecutionConflictError("Scoped frozen delivery authorization was not found")
    target = await db.get(DeliveryTargetRevision, decision.target_revision_id, with_for_update=True)
    if target is None or (target.target_id, target.revision, target.endpoint_identity, target.non_secret_config_hash, target.policy_hash) != (decision.target_id, decision.target_revision, decision.endpoint_identity, decision.non_secret_config_hash, decision.policy_hash):
        raise DeliveryExecutionConflictError("Frozen target revision no longer matches authorization")
    return decision


async def _claim(db: AsyncSession, scope: DeliveryAuthorizationScope, decision: DeliveryAuthorizationDecisionV1) -> DeliveryExecution:
    binding = _binding(decision)
    existing = await db.scalar(select(DeliveryExecution).where(DeliveryExecution.decision_id == decision.id).with_for_update())
    if existing is not None:
        if existing.execution_binding_hash != binding:
            raise DeliveryExecutionConflictError("Execution binding conflicts with existing frozen decision execution")
        return existing
    execution = DeliveryExecution(
        decision_id=decision.id,
        target_revision_id=decision.target_revision_id,
        workspace_id=scope.workspace_id,
        project_id=scope.project_id,
        workflow_id=scope.workflow_id,
        studio_workflow_version_id=scope.studio_workflow_version_id,
        run_id=scope.run_id,
        operation_id=decision.operation_id,
        decision_hash=decision.decision_hash,
        payload_hash=decision.payload_hash,
        execution_binding_hash=binding,
        state="pending",
    )
    db.add(execution)
    try:
        await db.flush()
        return execution
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(select(DeliveryExecution).where(DeliveryExecution.decision_id == decision.id))
        if existing is None or existing.execution_binding_hash != binding:
            raise DeliveryExecutionConflictError("Concurrent execution claim conflicts")
        return existing


async def _record(
    db: AsyncSession, execution: DeliveryExecution, *, attempt: int, transport: str, http_status: int | None,
    receipt: str, protocol: str, outcome: str, receipt_id: str | None = None, receipt_hash: str | None = None,
) -> DeliveryExecutionResult:
    result = DeliveryExecutionResult(
        execution_id=execution.id,
        attempt_number=attempt,
        transport_classification=transport,
        http_status=http_status,
        receipt_classification=receipt,
        protocol_classification=protocol,
        outcome=outcome,
        receipt_id=receipt_id,
        receipt_hash=receipt_hash,
        observed_at=_now(),
    )
    db.add(result)
    await db.flush()
    return result


async def execute_delivery(db: AsyncSession, *, scope: DeliveryAuthorizationScope, decision_id: str) -> DeliveryExecutionReadV1:
    decision = await _scoped_decision(db, scope, decision_id)
    payload = _payload(decision)
    execution = await _claim(db, scope, decision)
    prior = await _results(db, execution.id)
    if execution.final_outcome is not None:
        return _read(execution, prior)
    if execution.lease_token:
        # An active lease belongs to a concurrent sender. A lease stale beyond
        # the bounded recovery window is ambiguous and is never resent.
        if execution.lease_acquired_at is None or execution.lease_acquired_at <= _now() - timedelta(seconds=60):
            result = await _record(db, execution, attempt=len(prior) + 1, transport="crash-ambiguous", http_status=None, receipt="missing", protocol="unknown", outcome="unknown")
            execution.state, execution.final_outcome, execution.final_result_id, execution.lease_token = "blocked", "unknown", result.id, None
            await db.flush()
            return _read(execution, await _results(db, execution.id))
        return _read(execution, prior)
    if execution.cancel_requested_at:
        execution.state, execution.final_outcome = "cancelled", "unknown"
        await db.flush()
        return _read(execution, prior)

    target = await db.get(DeliveryTargetRevision, decision.target_revision_id)
    if target is None:
        raise DeliveryExecutionConflictError("Frozen delivery target revision is missing")
    endpoint = resolve_endpoint(target.endpoint_identity, target.credential_reference)
    body_value = {
        "version": "v2",
        "receiverIdentity": endpoint.receiver_identity,
        "operationId": decision.operation_id,
        "decisionHash": decision.decision_hash,
        "payloadHash": decision.payload_hash,
        "payload": payload,
    }
    body = canonical_json(body_value)
    timeout = float(decision.policy_snapshot.get("timeout", {}).get("perAttemptSeconds", 30))
    max_attempts = int(decision.policy_snapshot.get("retry", {}).get("maxAttempts", 3))
    for attempt in range(len(prior) + 1, max_attempts + 1):
        if execution.cancel_requested_at:
            execution.state, execution.final_outcome = "cancelled", "unknown"
            await db.flush()
            return _read(execution, await _results(db, execution.id))
        execution.state, execution.lease_token, execution.lease_acquired_at = "in-flight", base64.urlsafe_b64encode(f"{execution.id}:{attempt}".encode()).decode(), _now()
        await db.commit()  # reservation is durable before any network I/O
        headers = request_headers(body=body, endpoint=endpoint, operation_id=decision.operation_id, decision_hash=decision.decision_hash, payload_hash=decision.payload_hash)
        transport, http_status, receipt_classification, protocol, outcome, receipt_id, receipt_hash = "network-error", None, "missing", "unknown", "unknown", None, None
        retry = False
        try:
            response = await pinned_post(endpoint, body, headers, timeout_seconds=timeout)
            http_status = response.status_code
            transport = "http-5xx" if response.status_code >= 500 else "http-4xx" if response.status_code >= 400 else "http-success" if 200 <= response.status_code < 300 else "http-other"
            try:
                receipt_value = response.json().get("receipt")
                status = verify_receipt(receipt=receipt_value, endpoint=endpoint, operation_id=decision.operation_id, decision_hash=decision.decision_hash, payload_hash=decision.payload_hash)
                receipt_classification, protocol, outcome = "verified", "v2", status
                receipt_id, receipt_hash = receipt_value["receiptId"], canonical_hash(receipt_value)
            except (ValueError, ControlledReceiverSecurityError, AttributeError):
                receipt_classification = "invalid-or-missing"
                retry = response.status_code >= 500
        except httpx.TimeoutException:
            transport, receipt_classification, retry = "transport-timeout", "missing", True
        except ControlledReceiverSecurityError:
            transport, receipt_classification, protocol = "protocol-error", "missing", "invalid"
        except httpx.HTTPError:
            transport, receipt_classification, retry = "network-error", "missing", True
        await db.refresh(execution)
        result = await _record(db, execution, attempt=attempt, transport=transport, http_status=http_status, receipt=receipt_classification, protocol=protocol, outcome=outcome, receipt_id=receipt_id, receipt_hash=receipt_hash)
        execution.lease_token, execution.lease_acquired_at = None, None
        if execution.cancel_requested_at:
            execution.state, execution.final_outcome, execution.final_result_id = "cancelled", outcome, result.id
            await db.flush()
            return _read(execution, await _results(db, execution.id))
        if outcome in {"accepted", "rejected"}:
            execution.state, execution.final_outcome, execution.final_result_id = "completed", outcome, result.id
            await db.flush()
            return _read(execution, await _results(db, execution.id))
        if not retry or attempt == max_attempts:
            execution.state, execution.final_outcome, execution.final_result_id = "blocked", "unknown", result.id
            await db.flush()
            return _read(execution, await _results(db, execution.id))
        await db.commit()
        await asyncio.sleep(1 if attempt == 1 else 2)
    raise AssertionError("delivery retry loop exhausted unexpectedly")


async def get_delivery_execution(db: AsyncSession, *, scope: DeliveryAuthorizationScope, execution_id: str) -> DeliveryExecutionReadV1:
    execution = await db.scalar(select(DeliveryExecution).where(
        DeliveryExecution.id == execution_id, DeliveryExecution.workspace_id == scope.workspace_id,
        DeliveryExecution.project_id == scope.project_id, DeliveryExecution.workflow_id == scope.workflow_id,
        DeliveryExecution.studio_workflow_version_id == scope.studio_workflow_version_id, DeliveryExecution.run_id == scope.run_id,
    ))
    if execution is None:
        raise DeliveryExecutionConflictError("Scoped delivery execution was not found")
    return _read(execution, await _results(db, execution.id))


async def list_delivery_executions(db: AsyncSession, *, scope: DeliveryAuthorizationScope, cursor: str | None = None, limit: int = 50) -> DeliveryExecutionListV1:
    after = base64.urlsafe_b64decode(cursor.encode()).decode() if cursor else None
    stmt = select(DeliveryExecution).where(
        DeliveryExecution.workspace_id == scope.workspace_id, DeliveryExecution.project_id == scope.project_id,
        DeliveryExecution.workflow_id == scope.workflow_id, DeliveryExecution.studio_workflow_version_id == scope.studio_workflow_version_id,
        DeliveryExecution.run_id == scope.run_id,
    ).order_by(DeliveryExecution.id)
    if after:
        stmt = stmt.where(DeliveryExecution.id > after)
    rows = list((await db.execute(stmt.limit(max(1, min(limit, 200)) + 1))).scalars())
    page = rows[: max(1, min(limit, 200))]
    return DeliveryExecutionListV1(items=[_read(row, await _results(db, row.id)) for row in page], next_cursor=base64.urlsafe_b64encode(page[-1].id.encode()).decode() if len(rows) > len(page) and page else None)


async def cancel_delivery_execution(db: AsyncSession, *, scope: DeliveryAuthorizationScope, execution_id: str) -> DeliveryExecutionReadV1:
    execution = await db.scalar(select(DeliveryExecution).where(DeliveryExecution.id == execution_id, DeliveryExecution.workspace_id == scope.workspace_id).with_for_update())
    if execution is None or (execution.project_id, execution.workflow_id, execution.studio_workflow_version_id, execution.run_id) != (scope.project_id, scope.workflow_id, scope.studio_workflow_version_id, scope.run_id):
        raise DeliveryExecutionConflictError("Scoped delivery execution was not found")
    if execution.final_outcome is None:
        execution.cancel_requested_at = _now()
        if execution.state != "in-flight":
            execution.state, execution.final_outcome = "cancelled", "unknown"
        await db.flush()
    return _read(execution, await _results(db, execution.id))


async def reconcile_delivery_execution(
    db: AsyncSession, *, scope: DeliveryAuthorizationScope, execution_id: str
) -> DeliveryExecutionReadV1:
    """Query the durable receiver status without ever resending a delivery."""
    execution = await db.scalar(select(DeliveryExecution).where(
        DeliveryExecution.id == execution_id,
        DeliveryExecution.workspace_id == scope.workspace_id,
        DeliveryExecution.project_id == scope.project_id,
        DeliveryExecution.workflow_id == scope.workflow_id,
        DeliveryExecution.studio_workflow_version_id == scope.studio_workflow_version_id,
        DeliveryExecution.run_id == scope.run_id,
    ).with_for_update())
    if execution is None:
        raise DeliveryExecutionConflictError("Scoped delivery execution was not found")
    if execution.final_outcome != "unknown":
        return _read(execution, await _results(db, execution.id))
    decision = await _scoped_decision(db, scope, execution.decision_id)
    payload = _payload(decision)
    target = await db.get(DeliveryTargetRevision, decision.target_revision_id)
    if target is None:
        raise DeliveryExecutionConflictError("Frozen delivery target revision is missing")
    endpoint = resolve_endpoint(target.endpoint_identity, target.credential_reference)
    body = canonical_json({
        "version": "v2", "receiverIdentity": endpoint.receiver_identity,
        "operationId": decision.operation_id, "decisionHash": decision.decision_hash,
        "payloadHash": decision.payload_hash, "payload": payload,
    })
    headers = request_headers(body=body, endpoint=endpoint, operation_id=decision.operation_id, decision_hash=decision.decision_hash, payload_hash=decision.payload_hash)
    prior = await _results(db, execution.id)
    try:
        response = await pinned_post(endpoint, body, headers, timeout_seconds=float(decision.policy_snapshot.get("timeout", {}).get("perAttemptSeconds", 30)), status_query=True)
        receipt_value = response.json().get("receipt")
        outcome = verify_receipt(receipt=receipt_value, endpoint=endpoint, operation_id=decision.operation_id, decision_hash=decision.decision_hash, payload_hash=decision.payload_hash)
        result = await _record(db, execution, attempt=len(prior) + 1, transport="reconcile-http", http_status=response.status_code, receipt="verified", protocol="v2-status", outcome=outcome, receipt_id=receipt_value["receiptId"], receipt_hash=canonical_hash(receipt_value))
    except (httpx.HTTPError, ControlledReceiverSecurityError, ValueError, AttributeError) as exc:
        raise DeliveryExecutionConflictError("Controlled receiver reconciliation remains unknown") from exc
    execution.state, execution.final_outcome, execution.final_result_id = "completed", outcome, result.id
    await db.flush()
    return _read(execution, await _results(db, execution.id))
