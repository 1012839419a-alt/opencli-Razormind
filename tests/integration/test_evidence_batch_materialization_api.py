"""Public Admin/Studio EvidenceBatch materialization contracts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.models.iii_collection import IIICollectionAttemptV1, IIICollectionCommandV1
from backend.odp.query_client import OdpQueryUnavailable
from backend.workflow.iii_collection_store import _attempt_and_outbound
from tests.integration.iii_collection_test_support import (
    create_scoped_run,
    report_body,
    route,
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
