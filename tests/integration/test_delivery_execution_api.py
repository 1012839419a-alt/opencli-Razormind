"""Integration contracts for the separately authenticated durable receiver surface."""

import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.config import get_settings
from backend.main import app
from backend.models.delivery_authorization import DeliveryAuthorizationDecisionV1, DeliveryTarget, DeliveryTargetRevision
from backend.models.delivery_execution import (
    ControlledReceiverDelivery,
    ControlledReceiverNonce,
    DeliveryExecution,
    DeliveryExecutionReconciliation,
    DeliveryExecutionResult,
)
from backend.models.identity import User, Workspace, WorkspaceMembership, WorkspaceRole
from backend.security import controlled_receiver as receiver
from backend.security.identity import RequestIdentity, get_request_identity
from backend.workflow.delivery_authorization import DeliveryAuthorizationScope
from backend.workflow import delivery_execution
from tests.integration.iii_collection_test_support import create_scoped_run


@pytest.fixture(autouse=True)
def receiver_registry(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "controlled_receiver_registry_json", json.dumps({"receiver-primary": {"url": "https://receiver.example/deliver", "receiverIdentity": "receiver-a", "credentialReference": "credential-a", "requestKeyId": "request-a", "receiptKeyId": "receipt-a", "allowedNetworks": ["93.184.216.0/24"], "durableStatus": "accepted"}}))
    request_secret = "request-secret-that-is-at-least-thirty-two-bytes"
    receipt_secret = "receipt-secret-that-is-at-least-thirty-two-bytes"
    monkeypatch.setattr(settings, "controlled_receiver_credentials_json", json.dumps({"credential-a": request_secret}))
    monkeypatch.setattr(settings, "controlled_receiver_inbound_keys_json", json.dumps({"request-a": request_secret}))
    monkeypatch.setattr(settings, "controlled_receiver_receipt_keys_json", json.dumps({"receipt-a": receipt_secret}))


def _request():
    payload = {"schemaVersion": "delivery-claim-manifest-v1", "claims": [{"claimId": "claim-1", "contentHash": "a" * 64}], "manifestHashes": ["b" * 64]}
    return {"version": "v2", "receiverIdentity": "receiver-a", "operationId": "op-1", "decisionHash": "d" * 64, "payloadHash": receiver.canonical_hash(payload), "payload": payload}


def _route(scope: DeliveryAuthorizationScope) -> str:
    return (
        f"/api/v1/workspaces/{scope.workspace_id}/projects/{scope.project_id}"
        f"/workflows/{scope.workflow_id}/runs/{scope.run_id}/delivery-executions"
    )


async def _stored_frozen_decision(db_session) -> tuple[DeliveryAuthorizationScope, str]:
    scoped = await create_scoped_run(db_session)
    workspace_id = scoped["workspace"].id
    await db_session.merge(Workspace(id=workspace_id, name="Receiver delivery", slug="receiver-delivery"))
    scope = DeliveryAuthorizationScope(
        workspace_id=workspace_id,
        project_id=scoped["project"].id,
        workflow_id=scoped["workflow"].id,
        studio_workflow_version_id=scoped["version"].id,
        run_id=scoped["run"].id,
    )
    endpoint = receiver.resolve_endpoint("receiver-primary", "credential-a")
    policy_version, policy_snapshot, policy_hash = delivery_execution._current_policy()
    target_id, revision_id, decision_id = (str(uuid.uuid4()) for _ in range(3))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    claims = [{"claimId": "claim-1", "contentHash": "a" * 64}]
    manifests = [{"manifestHash": "b" * 64}]
    payload = {"schemaVersion": "delivery-claim-manifest-v1", "claims": claims, "manifestHashes": ["b" * 64]}
    target = DeliveryTarget(id=target_id, workspace_id=workspace_id, receiver_identity=endpoint.receiver_identity)
    revision = DeliveryTargetRevision(
        id=revision_id, target_id=target_id, revision=1, workspace_id=scope.workspace_id,
        project_id=scope.project_id, workflow_id=scope.workflow_id,
        studio_workflow_version_id=scope.studio_workflow_version_id, run_id=scope.run_id,
        endpoint_identity=endpoint.identity, non_secret_config_hash=receiver.endpoint_config_hash(endpoint),
        credential_reference=endpoint.credential_reference, policy_version=policy_version,
        policy_snapshot=policy_snapshot, policy_hash=policy_hash,
    )
    decision = DeliveryAuthorizationDecisionV1(
        id=decision_id, version="v1", workspace_id=scope.workspace_id, project_id=scope.project_id,
        workflow_id=scope.workflow_id, studio_workflow_version_id=scope.studio_workflow_version_id,
        run_id=scope.run_id, node_id="delivery-node", operation_id="delivery-op",
        idempotency_key="delivery-idempotency", target_id=target_id, target_revision_id=revision_id,
        target_revision=1, endpoint_identity=endpoint.identity,
        non_secret_config_hash=receiver.endpoint_config_hash(endpoint), policy_version=policy_version,
        policy_snapshot=policy_snapshot, policy_hash=policy_hash, pin_sequence=1,
        research_revision_id="research-1", manifest_set_hash="b" * 64, selected_claims=claims,
        manifest_set=manifests,
        sanitized_payload_manifest={
            "payloadSchemaVersion": "delivery-claim-manifest-v1",
            "payloadReference": "frozen-claim-manifest",
            "payloadHash": receiver.canonical_hash(payload),
            "sanctionedReferenceHashes": ["a" * 64, "b" * 64],
            "redactionProfileVersion": "delivery-authorization-redaction-v1",
        },
        payload_schema_version="delivery-claim-manifest-v1", payload_reference="frozen-claim-manifest",
        payload_hash=receiver.canonical_hash(payload), redaction_profile_version="delivery-authorization-redaction-v1",
        approver_actor_id="approver-1", approver_actor_type="user", approver_principal="approver-1",
        approver_capability="actions.approve", approval_policy_version="workspace-rbac-v1",
        approved_at=now, approval_evidence=[], binding_hash="", decision_hash="", decisioned_at=now,
    )
    decision.approval_evidence = [delivery_execution._approval(decision, scope)]
    binding = delivery_execution._decision_binding(decision, scope)
    decision.binding_hash = receiver.canonical_hash(binding)
    decision.decision_hash = receiver.canonical_hash(
        {"binding": binding, "approvalEvidence": decision.approval_evidence, "decisionedAt": now.isoformat()}
    )
    db_session.add_all((target, revision, decision))
    await db_session.commit()
    return scope, decision_id


@pytest.mark.asyncio
async def test_durable_receiver_exact_duplicate_returns_same_signed_receipt_after_commit(client: AsyncClient):
    value = _request()
    body = receiver.canonical_json(value)
    endpoint = receiver.resolve_endpoint("receiver-primary", "credential-a")
    headers = receiver.request_headers(body=body, endpoint=endpoint, operation_id=value["operationId"], decision_hash=value["decisionHash"], payload_hash=value["payloadHash"])
    first = await client.post("/api/v1/controlled-receiver/v2/deliver", content=body, headers=headers)
    second = await client.post("/api/v1/controlled-receiver/v2/deliver", content=body, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["receipt"] == second.json()["receipt"]


@pytest.mark.asyncio
async def test_controlled_receiver_rejects_unauthenticated_body(client: AsyncClient):
    response = await client.post("/api/v1/controlled-receiver/v2/deliver", content=receiver.canonical_json(_request()), headers={"Content-Type": "application/json"})
    assert response.status_code == 401



@pytest.mark.asyncio
async def test_receiver_v2_mac_auth_is_independent_of_fleet_bearer(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_auth_token", "fleet-token")
    value = _request()
    body = receiver.canonical_json(value)
    endpoint = receiver.resolve_endpoint("receiver-primary", "credential-a")
    headers = receiver.request_headers(body=body, endpoint=endpoint, operation_id=value["operationId"], decision_hash=value["decisionHash"], payload_hash=value["payloadHash"])
    assert (await client.post("/api/v1/controlled-receiver/v2/deliver", content=body, headers=headers)).status_code == 200
    assert (await client.get("/api/v1/system/config")).status_code == 401


@pytest.mark.asyncio
async def test_durable_receiver_conflicts_on_changed_request_binding(client: AsyncClient):
    value = _request()
    endpoint = receiver.resolve_endpoint("receiver-primary", "credential-a")
    body = receiver.canonical_json(value)
    headers = receiver.request_headers(body=body, endpoint=endpoint, operation_id=value["operationId"], decision_hash=value["decisionHash"], payload_hash=value["payloadHash"])
    assert (await client.post("/api/v1/controlled-receiver/v2/deliver", content=body, headers=headers)).status_code == 200
    changed = _request()
    changed["payload"]["claims"][0]["contentHash"] = "c" * 64
    changed["payloadHash"] = receiver.canonical_hash(changed["payload"])
    changed_body = receiver.canonical_json(changed)
    changed_headers = receiver.request_headers(body=changed_body, endpoint=endpoint, operation_id=changed["operationId"], decision_hash=changed["decisionHash"], payload_hash=changed["payloadHash"])
    assert (await client.post("/api/v1/controlled-receiver/v2/deliver", content=changed_body, headers=changed_headers)).status_code == 409


@pytest.mark.asyncio
async def test_receiver_status_requires_exact_durable_request_binding(client: AsyncClient):
    value = _request()
    endpoint = receiver.resolve_endpoint("receiver-primary", "credential-a")
    body = receiver.canonical_json(value)
    headers = receiver.request_headers(body=body, endpoint=endpoint, operation_id=value["operationId"], decision_hash=value["decisionHash"], payload_hash=value["payloadHash"])
    assert (await client.post("/api/v1/controlled-receiver/v2/deliver", content=body, headers=headers)).status_code == 200
    changed = _request()
    changed["payload"]["claims"][0]["contentHash"] = "c" * 64
    changed["payloadHash"] = receiver.canonical_hash(changed["payload"])
    changed_body = receiver.canonical_json(changed)
    changed_headers = receiver.request_headers(body=changed_body, endpoint=endpoint, operation_id=changed["operationId"], decision_hash=changed["decisionHash"], payload_hash=changed["payloadHash"])
    assert (await client.post("/api/v1/controlled-receiver/v2/status", content=changed_body, headers=changed_headers)).status_code == 409


@pytest.mark.asyncio
async def test_receiver_v2_mac_exemption_does_not_accept_invalid_mac_or_oversized_body(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_auth_token", "fleet-token")
    value = _request()
    body = receiver.canonical_json(value)
    endpoint = receiver.resolve_endpoint("receiver-primary", "credential-a")
    headers = receiver.request_headers(body=body, endpoint=endpoint, operation_id=value["operationId"], decision_hash=value["decisionHash"], payload_hash=value["payloadHash"])
    headers["X-Controlled-Receiver-Mac"] = "invalid"
    assert (await client.post("/api/v1/controlled-receiver/v2/deliver", content=body, headers=headers)).status_code == 401
    assert (await client.post("/api/v1/controlled-receiver/v2/deliver", content=b"x" * (64 * 1024 + 1), headers={"Content-Type": "application/json"})).status_code == 413


@pytest.mark.asyncio
async def test_executor_sends_to_durable_receiver_and_replays_one_verified_receipt(client: AsyncClient, db_session, monkeypatch):
    scope, decision_id = await _stored_frozen_decision(db_session)

    async def send_to_durable_receiver(endpoint, body, headers, *, timeout_seconds, status_query=False):
        path = "/api/v1/controlled-receiver/v2/status" if status_query else "/api/v1/controlled-receiver/v2/deliver"
        return await client.post(path, content=body, headers=headers)

    monkeypatch.setattr(delivery_execution, "pinned_post", send_to_durable_receiver)
    first = await delivery_execution.execute_delivery(db_session, scope=scope, decision_id=decision_id)
    await db_session.commit()
    replay = await delivery_execution.execute_delivery(db_session, scope=scope, decision_id=decision_id)
    assert first.outcome == replay.outcome == "accepted"
    assert first.attempt_count == replay.attempt_count == 1
    assert (await db_session.execute(select(ControlledReceiverDelivery))).scalars().all()[0].operation_id == "delivery-op"
    execution = await db_session.scalar(select(DeliveryExecution).where(DeliveryExecution.decision_id == decision_id))
    execution.state, execution.final_outcome = "blocked", "unknown"
    await db_session.commit()
    reconciled = await delivery_execution.reconcile_delivery_execution(
        db_session, scope=scope, execution_id=execution.id
    )
    assert reconciled.outcome == "accepted"
    assert reconciled.attempt_count == 1
    assert len(reconciled.reconciliations) == 1
    await db_session.commit()
    stable = await delivery_execution.get_delivery_execution(db_session, scope=scope, execution_id=execution.id)
    assert stable.attempt_count == 1
    assert [(item.outcome, item.receipt_hash) for item in stable.reconciliations] == [
        (item.outcome, item.receipt_hash) for item in reconciled.reconciliations
    ]


@pytest.mark.asyncio
async def test_execution_and_read_survive_recreated_database_sessions(client: AsyncClient, db_session, monkeypatch):
    scope, decision_id = await _stored_frozen_decision(db_session)

    async def send_to_durable_receiver(endpoint, body, headers, *, timeout_seconds, status_query=False):
        path = "/api/v1/controlled-receiver/v2/status" if status_query else "/api/v1/controlled-receiver/v2/deliver"
        return await client.post(path, content=body, headers=headers)

    monkeypatch.setattr(delivery_execution, "pinned_post", send_to_durable_receiver)
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with sessions() as executing_session:
        executed = await delivery_execution.execute_delivery(executing_session, scope=scope, decision_id=decision_id)
        await executing_session.commit()
    async with sessions() as recreated_session:
        recovered = await delivery_execution.get_delivery_execution(
            recreated_session, scope=scope, execution_id=executed.execution_id
        )
    assert recovered.outcome == "accepted"
    assert recovered.attempt_count == 1


@pytest.mark.asyncio
async def test_studio_execution_routes_preserve_durable_attempt_and_reconciliation_evidence(client: AsyncClient, db_session, monkeypatch):
    scope, decision_id = await _stored_frozen_decision(db_session)
    manager = User(id="delivery-execution-manager", subject="delivery-execution-manager")
    db_session.add_all((
        manager,
        WorkspaceMembership(
            workspace_id=scope.workspace_id, user_id=manager.id, role=WorkspaceRole.MAINTAINER
        ),
    ))
    await db_session.commit()

    async def override_identity():
        return RequestIdentity(subject=manager.subject)

    async def send_to_durable_receiver(endpoint, body, headers, *, timeout_seconds, status_query=False):
        path = "/api/v1/controlled-receiver/v2/status" if status_query else "/api/v1/controlled-receiver/v2/deliver"
        return await client.post(path, content=body, headers=headers)

    app.dependency_overrides[get_request_identity] = override_identity
    monkeypatch.setattr(delivery_execution, "pinned_post", send_to_durable_receiver)
    try:
        route = _route(scope)
        created = await client.post(route, json={"decisionId": decision_id})
        assert created.status_code == 201
        execution = created.json()["data"]
        assert execution["outcome"] == "accepted"
        assert execution["attemptCount"] == 1

        read = await client.get(f"{route}/{execution['executionId']}")
        listed = await client.get(route)
        assert read.status_code == listed.status_code == 200
        assert read.json()["data"]["executionId"] == execution["executionId"]
        assert [item["executionId"] for item in listed.json()["data"]["items"]] == [execution["executionId"]]

        cancelled = await client.post(f"{route}/{execution['executionId']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["data"]["outcome"] == "accepted"

        row = await db_session.get(DeliveryExecution, execution["executionId"])
        row.state, row.final_outcome = "blocked", "unknown"
        await db_session.commit()
        reconciled = await client.post(f"{route}/{execution['executionId']}/reconcile")
        assert reconciled.status_code == 200
        assert reconciled.json()["data"]["outcome"] == "accepted"
        assert reconciled.json()["data"]["attemptCount"] == 1
        assert len(reconciled.json()["data"]["reconciliations"]) == 1
    finally:
        app.dependency_overrides.pop(get_request_identity, None)


@pytest.mark.asyncio
async def test_sqlite_raw_evidence_mutations_are_rejected_after_durable_execution(client: AsyncClient, db_session, monkeypatch):
    scope, decision_id = await _stored_frozen_decision(db_session)

    async def send_to_receiver(endpoint, body, headers, *, timeout_seconds, status_query=False):
        path = "/api/v1/controlled-receiver/v2/status" if status_query else "/api/v1/controlled-receiver/v2/deliver"
        return await client.post(path, content=body, headers=headers)

    monkeypatch.setattr(delivery_execution, "pinned_post", send_to_receiver)
    delivered = await delivery_execution.execute_delivery(db_session, scope=scope, decision_id=decision_id)
    execution = await db_session.get(DeliveryExecution, delivered.execution_id)
    execution.state, execution.final_outcome = "blocked", "unknown"
    await db_session.commit()
    await delivery_execution.reconcile_delivery_execution(db_session, scope=scope, execution_id=execution.id)
    await db_session.commit()
    for table in (
        "delivery_execution_results", "delivery_execution_reconciliations",
        "controlled_receiver_deliveries", "controlled_receiver_nonces",
    ):
        await db_session.execute(text(
            f"CREATE TRIGGER raw_guard_{table}_update BEFORE UPDATE ON {table} "
            f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"
        ))
        await db_session.execute(text(
            f"CREATE TRIGGER raw_guard_{table}_delete BEFORE DELETE ON {table} "
            f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"
        ))
    await db_session.execute(text(
        "CREATE TRIGGER raw_result_checks BEFORE INSERT ON delivery_execution_results "
        "WHEN NEW.attempt_number NOT BETWEEN 1 AND 3 OR NEW.outcome NOT IN ('accepted','rejected','unknown') "
        "BEGIN SELECT RAISE(ABORT, 'invalid result'); END"
    ))
    for event in ("INSERT", "UPDATE"):
        columns = "" if event == "INSERT" else " OF durable_status"
        await db_session.execute(text(
            f"CREATE TRIGGER raw_receiver_status_check_{event.lower()} BEFORE {event}{columns} "
            "ON controlled_receiver_deliveries WHEN NEW.durable_status NOT IN ('accepted','rejected') "
            "BEGIN SELECT RAISE(ABORT, 'invalid durable status'); END"
        ))
    await db_session.commit()
    async def rejected(statement: str, params: dict):
        with pytest.raises(IntegrityError):
            await db_session.execute(text(statement), params)
            await db_session.commit()
        await db_session.rollback()
    now = datetime.now(timezone.utc)

    result_execution_id = (await db_session.execute(select(DeliveryExecutionResult.execution_id))).scalar_one()
    for attempt, outcome in ((0, "unknown"), (4, "unknown"), (1, "invalid")):
        await rejected(
            "INSERT INTO delivery_execution_results "
            "(id, created_at, updated_at, execution_id, attempt_number, transport_classification, "
            "receipt_classification, protocol_classification, outcome, observed_at) "
            "VALUES (:id, :now, :now, :execution_id, :attempt, 'test', 'missing', 'unknown', :outcome, :now)",
            {"id": str(uuid.uuid4()), "now": now, "execution_id": result_execution_id, "attempt": attempt, "outcome": outcome},
        )
    await rejected(
        "INSERT INTO controlled_receiver_deliveries "
        "(id, created_at, updated_at, receiver_identity, operation_id, decision_hash, payload_hash, request_hash, "
        "durable_status, receipt_id, receipt_timestamp, receipt_key_id, receipt_signature) "
        "VALUES (:id, :now, :now, 'receiver-a', 'invalid-status', :hash, :hash, :hash, 'invalid', :receipt, :now, 'receipt-a', 'signature')",
        {"id": str(uuid.uuid4()), "now": now, "hash": "f" * 64, "receipt": f"receipt-{uuid.uuid4().hex}"},
    )
    for table in (
        "delivery_execution_results", "delivery_execution_reconciliations",
        "controlled_receiver_deliveries", "controlled_receiver_nonces",
    ):
        with pytest.raises(IntegrityError):
            await db_session.execute(text(f"UPDATE {table} SET updated_at = updated_at"))
            await db_session.commit()
        await db_session.rollback()
        with pytest.raises(IntegrityError):
            await db_session.execute(text(f"DELETE FROM {table}"))
            await db_session.commit()
        await db_session.rollback()


@pytest.mark.asyncio
async def test_two_sessions_cancel_before_send_start_prevents_post_and_result(db_session, db_engine, monkeypatch):
    scope, decision_id = await _stored_frozen_decision(db_session)
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    reserved = asyncio.Event()
    release = asyncio.Event()
    posts = []

    async def hold_before_send(**_kwargs):
        reserved.set()
        await release.wait()

    async def no_post(*_args, **_kwargs):
        posts.append(True)
        raise AssertionError("cancelled reservation must not post")

    monkeypatch.setattr(delivery_execution, "_before_send_start", hold_before_send)
    monkeypatch.setattr(delivery_execution, "pinned_post", no_post)
    async with sessions() as executing, sessions() as cancelling:
        task = asyncio.create_task(
            delivery_execution.execute_delivery(executing, scope=scope, decision_id=decision_id)
        )
        await reserved.wait()
        execution = await cancelling.scalar(
            select(DeliveryExecution).where(DeliveryExecution.decision_id == decision_id)
        )
        await delivery_execution.cancel_delivery_execution(cancelling, scope=scope, execution_id=execution.id)
        await cancelling.commit()
        release.set()
        result = await task
    assert result.outcome == "unknown"
    assert result.state == "cancelled"
    assert posts == []
    assert result.attempt_count == 0