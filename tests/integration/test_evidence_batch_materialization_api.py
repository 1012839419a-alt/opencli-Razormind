"""Public Admin/Studio EvidenceBatch materialization contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.models.iii_collection import (
    IIICollectionAttemptV1,
    IIICollectionCommandV1,
    IIICollectionExpectedKeyReportV1,
    IIICollectionIngressReceiptV1,
)
from backend.odp.query_client import OdpQueryUnavailable, OdpRecordKey
from backend.workflow.evidence_batch_materialization_facts import receipt_outcomes
from backend.workflow.evidence_batch_materializer import (
    get_materialization,
    materialize_evidence_batch,
)
from backend.workflow.iii_collection_store import (
    CollectionScope,
    IIICollectionNotFoundError,
    _attempt_and_outbound,
)
from tests.integration.iii_collection_test_support import (
    create_scoped_run,
    receipt_body,
    report_body,
    route,
    sign_receipt_body,
    submit_body,
    submit_report_and_receipt,
)

def _record(command, event_id: str = "event-1", record_id: int = 42) -> dict:
    return {
        "source_id": command.odp_source_id,
        "event_id": event_id,
        "odp_record_id": record_id,
        "committed_at": "2026-08-30T00:00:00Z",
        "provider": "test",
        "source_ts": "2026-08-30T00:00:00Z",
    }


def _base(request) -> dict:
    return {
        "query_fingerprint": request["delegation"]["query_fingerprint"],
        "retention_state": "unknown",
        "redaction_profile_version": "odp-query-reference-v1",
    }


def _completed_query(command, calls: list[str] | None = None):
    record = _record(command)

    async def query(request):
        if calls is not None:
            calls.append(request["mode"])
        if request["mode"] == "exact":
            return {
                **_base(request),
                "mode": "exact",
                "records": [record],
                "results": [
                    {
                        "key": {"source_id": command.odp_source_id, "event_id": "event-1"},
                        "classification": "present",
                        "retention_state": "unknown",
                        "record": record,
                    }
                ],
            }
        return {
            **_base(request),
            "mode": "attempt_page",
            "records": [record],
            "results": [],
            "as_of": "2026-08-30T00:00:00Z",
        }

    return query


def test_rejected_and_non_rejected_receipts_remain_indeterminate():
    key = OdpRecordKey(UUID("11111111-1111-4111-8111-111111111111"), "event-1")
    accepted = SimpleNamespace(
        outcomes=[
            {
                "source_id": str(key.source_id),
                "event_id": key.event_id,
                "outcome": "accepted",
            }
        ]
    )
    rejected = SimpleNamespace(
        outcomes=[
            {
                "source_id": str(key.source_id),
                "event_id": key.event_id,
                "outcome": "rejected",
            }
        ]
    )
    assert receipt_outcomes([accepted, rejected], [key]) is None


@pytest.mark.asyncio
async def test_materialization_requires_exact_presence_and_projects_completed(
    client, db_session, monkeypatch
):
    scope, command = await submit_report_and_receipt(client, db_session, monkeypatch)
    record = _record(command)

    async def query(request):
        if request["mode"] == "exact":
            return {
                **_base(request),
                "mode": "exact",
                "records": [record],
                "results": [
                    {
                        "key": {"source_id": command.odp_source_id, "event_id": "event-1"},
                        "classification": "present",
                        "retention_state": "unknown",
                        "record": record,
                    }
                ],
            }
        return {**_base(request), "mode": "attempt_page", "records": [record], "results": [], "as_of": "2026-08-30T00:00:00Z"}

    monkeypatch.setattr("backend.workflow.evidence_batch_materializer.post_reconciliation_query", query)
    response = await client.post(f"{route(scope)}/{command.id}/materialize")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["materializationStatus"] == "completed"
    assert data["legacyStatus"] == "completed"
    assert data["recordReferences"] == [{"sourceId": command.odp_source_id, "eventId": "event-1", "odpRecordId": 42, "committedAt": "2026-08-30T00:00:00Z"}]
    assert "receipt-secret" not in response.text


@pytest.mark.asyncio
async def test_declared_successful_zero_materializes_without_odp_query(client, db_session, monkeypatch):
    scope = await create_scoped_run(db_session)

    async def no_dispatch(db, *, command):
        _, outbound = await _attempt_and_outbound(db, command.id)
        return outbound

    monkeypatch.setattr("backend.api.v1.iii_collections.dispatch_collection_attempt", no_dispatch)
    monkeypatch.setattr("backend.api.v1.iii_collections.get_settings", lambda: SimpleNamespace(iii_lifecycle_token="bridge-token"))
    submitted = await client.post(route(scope), json=submit_body())
    command = await db_session.get(IIICollectionCommandV1, submitted.json()["data"]["commandId"])
    attempt = await db_session.get(IIICollectionAttemptV1, submitted.json()["data"]["attemptId"])
    assert command is not None and attempt is not None
    headers = {"x-iii-bridge-token": "bridge-token"}
    assert (await client.post("/api/v1/iii-collections/expected-key-reports", json=report_body(command, attempt, event_id=None), headers=headers)).status_code == 200

    async def must_not_query(_request):
        raise AssertionError("successful zero must not be inferred from ODP")

    monkeypatch.setattr("backend.workflow.evidence_batch_materializer.post_reconciliation_query", must_not_query)
    response = await client.post(f"{route(scope)}/{command.id}/materialize")
    assert response.status_code == 200
    assert response.json()["data"]["materializationStatus"] == "completed_empty"
    assert response.json()["data"]["legacyStatus"] == "completed"


@pytest.mark.asyncio
async def test_materialization_outage_is_indeterminate_and_recovery_appends_revision(
    client, db_session, monkeypatch
):
    scope, command = await submit_report_and_receipt(client, db_session, monkeypatch)
    recovered = False

    async def query(request):
        if request["mode"] == "attempt_page":
            if not recovered:
                raise OdpQueryUnavailable("cursor snapshot unavailable")
            return {**_base(request), "mode": "attempt_page", "records": [], "results": [], "as_of": "2026-08-30T00:00:00Z"}
        record = _record(command)
        return {**_base(request), "mode": "exact", "records": [record], "results": [{"key": {"source_id": command.odp_source_id, "event_id": "event-1"}, "classification": "present", "retention_state": "unknown", "record": record}]}

    monkeypatch.setattr("backend.workflow.evidence_batch_materializer.post_reconciliation_query", query)
    first = await client.post(f"{route(scope)}/{command.id}/materialize")
    assert first.status_code == 200
    assert first.json()["data"]["materializationStatus"] == "indeterminate"
    assert first.json()["data"]["legacyStatus"] == "blocked"
    assert first.json()["data"]["recoveryAction"] == "reconcile_evidence_batch"

    recovered = True
    second = await client.post(f"{route(scope)}/{command.id}/recover")
    assert second.status_code == 200
    assert second.json()["data"]["materializationStatus"] == "completed"
    assert second.json()["data"]["reconciliationRevision"] == 2


@pytest.mark.asyncio
async def test_explicit_signed_rejection_materializes_partial_not_completed(client, db_session, monkeypatch):
    scope, command = await submit_report_and_receipt(client, db_session, monkeypatch, outcome="rejected")

    async def query(request):
        assert request["mode"] == "attempt_page"
        return {**_base(request), "mode": "attempt_page", "records": [], "results": [], "as_of": "2026-08-30T00:00:00Z"}

    monkeypatch.setattr("backend.workflow.evidence_batch_materializer.post_reconciliation_query", query)
    response = await client.post(f"{route(scope)}/{command.id}/materialize")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["materializationStatus"] == "partial"
    assert data["legacyStatus"] == "partial"
    assert data["counts"]["rejected"] == 1
    assert data["recordReferences"] == []


@pytest.mark.asyncio
async def test_materialization_chunks_exact_keys_with_one_scope_fingerprint(client, db_session, monkeypatch):
    event_ids = [f"event-{index}" for index in range(101)]
    scope, command = await submit_report_and_receipt(client, db_session, monkeypatch, event_ids=event_ids)
    exact_requests: list[dict] = []

    async def query(request):
        if request["mode"] == "attempt_page":
            return {**_base(request), "mode": "attempt_page", "records": [], "results": [], "as_of": "2026-08-30T00:00:00Z"}
        exact_requests.append(request)
        records = [
            {"source_id": key["source_id"], "event_id": key["event_id"], "odp_record_id": index + 1, "committed_at": "2026-08-30T00:00:00Z", "provider": "test", "source_ts": "2026-08-30T00:00:00Z"}
            for index, key in enumerate(request["keys"])
        ]
        return {**_base(request), "mode": "exact", "records": records, "results": [{"key": {"source_id": record["source_id"], "event_id": record["event_id"]}, "classification": "present", "retention_state": "unknown", "record": record} for record in records]}

    monkeypatch.setattr("backend.workflow.evidence_batch_materializer.post_reconciliation_query", query)
    response = await client.post(f"{route(scope)}/{command.id}/materialize")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["materializationStatus"] == "completed"
    assert data["recordCount"] == 101
    assert len(data["recordReferences"]) == 101
    assert [len(request["keys"]) for request in exact_requests] == [100, 1]
    assert len({request["delegation"]["query_fingerprint"] for request in exact_requests}) == 1
    assert data["pageSnapshotAsOf"] == "2026-08-30T00:00:00Z"


@pytest.mark.asyncio
async def test_retry_receipts_merge_accepted_and_duplicate_as_non_rejected(
    client, db_session, monkeypatch
):
    scope, command = await submit_report_and_receipt(client, db_session, monkeypatch)
    attempt = (
        await db_session.execute(
            select(IIICollectionAttemptV1).where(IIICollectionAttemptV1.command_id == command.id)
        )
    ).scalar_one()
    assert attempt is not None
    retry = receipt_body(command, attempt, report_body(command, attempt))
    retry.update({"receiptId": "receipt-2", "idempotencyKey": "odp-ingest:receipt-2"})
    retry["outcomes"][0]["outcome"] = "duplicate"
    retry = sign_receipt_body(retry)
    headers = {"x-iii-bridge-token": "bridge-token"}
    assert (
        await client.post("/api/v1/iii-collections/ingress-receipts", json=retry, headers=headers)
    ).status_code == 200

    monkeypatch.setattr(
        "backend.workflow.evidence_batch_materializer.post_reconciliation_query",
        _completed_query(command),
    )
    response = await client.post(f"{route(scope)}/{command.id}/materialize")
    assert response.status_code == 200
    assert response.json()["data"]["materializationStatus"] == "completed"


@pytest.mark.asyncio
async def test_terminal_materialization_replays_without_querying_or_appending_revision(
    client, db_session, monkeypatch
):
    scope, command = await submit_report_and_receipt(client, db_session, monkeypatch)
    query_calls: list[str] = []
    monkeypatch.setattr(
        "backend.workflow.evidence_batch_materializer.post_reconciliation_query",
        _completed_query(command, query_calls),
    )

    first = await client.post(f"{route(scope)}/{command.id}/materialize")
    second = await client.post(f"{route(scope)}/{command.id}/materialize")

    assert first.status_code == second.status_code == 200
    assert query_calls == ["exact", "attempt_page"]
    assert first.json()["data"]["reconciliationRevision"] == 1
    assert second.json()["data"]["reconciliationRevision"] == 1
    assert second.json()["data"]["pageSnapshotAsOf"] == first.json()["data"]["pageSnapshotAsOf"]


@pytest.mark.asyncio
async def test_materialization_rejects_wrong_studio_workflow_version_scope(
    client, db_session, monkeypatch
):
    scope, command = await submit_report_and_receipt(client, db_session, monkeypatch)
    monkeypatch.setattr(
        "backend.workflow.evidence_batch_materializer.post_reconciliation_query",
        _completed_query(command),
    )
    assert (await client.post(f"{route(scope)}/{command.id}/materialize")).status_code == 200
    wrong_scope = CollectionScope(
        workspace_id=scope["workspace"].id,
        project_id=scope["project"].id,
        workflow_id=scope["workflow"].id,
        studio_workflow_version_id="another-published-version",
        run_id=scope["run"].id,
    )

    assert await get_materialization(db_session, scope=wrong_scope, command_id=command.id) is None
    with pytest.raises(IIICollectionNotFoundError):
        await materialize_evidence_batch(db_session, scope=wrong_scope, command_id=command.id)


@pytest.mark.asyncio
async def test_studio_evidence_routes_project_latest_redacted_scoped_status(
    client, db_session, monkeypatch
):
    scope, command = await submit_report_and_receipt(client, db_session, monkeypatch)
    monkeypatch.setattr(
        "backend.workflow.evidence_batch_materializer.post_reconciliation_query",
        _completed_query(command),
    )
    materialized = await client.post(f"{route(scope)}/{command.id}/materialize")
    assert materialized.status_code == 200
    batch_id = materialized.json()["data"]["batchId"]
    studio_run = route(scope).removesuffix("/iii-collections")

    listed = await client.get(f"{studio_run}/evidence-batches/v1")
    detail = await client.get(f"{studio_run}/evidence-batches/v1/{batch_id}")
    status_response = await client.get(f"{studio_run}/evidence-batches/v1/{batch_id}/status")
    wrong_scope = await client.get(
        f"{studio_run.replace('/workspaces/iii-workspace/', '/workspaces/other-workspace/')}"
        "/evidence-batches/v1"
    )

    assert listed.status_code == detail.status_code == status_response.status_code == 200
    assert wrong_scope.status_code == 404
    list_data = listed.json()["data"]
    assert list_data["runId"] == scope["run"].id
    assert list_data["evidenceBatches"][0]["materializationStatus"] == "completed"
    assert detail.json()["data"]["recordReferences"] == materialized.json()["data"]["recordReferences"]
    assert status_response.json()["data"]["legacyStatus"] == "completed"
    for forbidden in ("payloadSha256", "signature", "expectedKeySet", "rejectionReason"):
        assert forbidden not in detail.text


@pytest.mark.asyncio
async def test_integrity_race_returns_matching_persisted_winner(
    client, db_session, monkeypatch
):
    scope, command = await submit_report_and_receipt(client, db_session, monkeypatch)
    attempt = (
        await db_session.execute(
            select(IIICollectionAttemptV1).where(IIICollectionAttemptV1.command_id == command.id)
        )
    ).scalar_one()
    report = (
        await db_session.execute(
            select(IIICollectionExpectedKeyReportV1).where(
                IIICollectionExpectedKeyReportV1.attempt_id == attempt.id
            )
        )
    ).scalar_one()
    receipt = (
        await db_session.execute(
            select(IIICollectionIngressReceiptV1).where(
                IIICollectionIngressReceiptV1.attempt_id == attempt.id
            )
        )
    ).scalar_one()
    winner = SimpleNamespace(
        materialization_status="completed",
        batch_id="00000000-0000-0000-0000-000000000001",
        reconciliation_revision=1,
        item_count=report.item_count,
        counts={"expected": 1, "record_present": 1, "inserted": 0, "duplicate_existing": 0, "rejected": 0, "dlq": 0, "unknown": 0},
        record_references=[],
        finalization_reason="exact_presence_reconciled",
        query_fingerprint="0" * 64,
        page_snapshot_as_of="2026-08-30T00:00:00Z",
        redaction_profile_version="odp-query-reference-v1",
        finalized_at=datetime(2026, 8, 30, tzinfo=UTC),
        report_id=report.report_id,
        report_hash=report.report_hash,
        expected_key_set_hash=report.key_set_sha256,
        receipt_hashes=[receipt.receipt_hash],
    )
    latest_calls = 0

    async def latest_after_race(*_args):
        nonlocal latest_calls
        latest_calls += 1
        return winner if latest_calls == 3 else None

    async def duplicate_revision_flush():
        raise IntegrityError("insert materialization", {}, RuntimeError("concurrent winner"))

    monkeypatch.setattr(
        "backend.workflow.evidence_batch_materializer.post_reconciliation_query",
        _completed_query(command),
    )
    monkeypatch.setattr(
        "backend.workflow.evidence_batch_materializer._latest_manifest",
        latest_after_race,
    )
    monkeypatch.setattr(db_session, "flush", duplicate_revision_flush)
    result = await materialize_evidence_batch(
        db_session,
        scope=CollectionScope(
            workspace_id=scope["workspace"].id,
            project_id=scope["project"].id,
            workflow_id=scope["workflow"].id,
            studio_workflow_version_id=scope["version"].id,
            run_id=scope["run"].id,
        ),
        command_id=command.id,
    )

    assert latest_calls == 3
    assert result.reconciliation_revision == 1
    assert result.materialization_status == "completed"
