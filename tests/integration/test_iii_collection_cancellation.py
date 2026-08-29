"""Cancellation-precedence coverage for the III collection receipt vertical."""

from types import SimpleNamespace

import pytest

from backend.models.iii_collection import IIICollectionAttemptV1, IIICollectionCommandV1
from backend.workflow.iii_collection_store import _attempt_and_outbound, cancel_collection
from tests.integration.test_iii_collection_vertical import (
    _create_scoped_run,
    _receipt_body,
    _report_body,
    _route,
    _submit_body,
)


@pytest.mark.asyncio
async def test_late_facts_after_cancellation_preserve_cancellation_precedence(
    client, db_session, monkeypatch
):
    scope = await _create_scoped_run(db_session)

    async def no_dispatch(_db, *, command):
        _, outbound = await _attempt_and_outbound(_db, command.id)
        return outbound

    monkeypatch.setattr("backend.api.v1.iii_collections.dispatch_collection_attempt", no_dispatch)
    monkeypatch.setattr(
        "backend.api.v1.iii_collections.get_settings",
        lambda: SimpleNamespace(
            iii_lifecycle_token="bridge-token", iii_ingress_receipt_secret="receipt-secret"
        ),
    )
    monkeypatch.setattr(
        "backend.workflow.iii_collection_store.get_settings",
        lambda: SimpleNamespace(iii_ingress_receipt_secret="receipt-secret"),
    )
    submitted = await client.post(_route(scope), json=_submit_body())
    command = await db_session.get(IIICollectionCommandV1, submitted.json()["data"]["commandId"])
    attempt = await db_session.get(IIICollectionAttemptV1, submitted.json()["data"]["attemptId"])
    assert command is not None and attempt is not None

    _, outbound = await _attempt_and_outbound(db_session, command.id)
    outbound.state = "bridge_accepted"
    await db_session.commit()
    await cancel_collection(db_session, command=command)

    report = _report_body(command, attempt)
    receipt = _receipt_body(command, attempt, report)
    headers = {"x-iii-bridge-token": "bridge-token"}
    assert (
        await client.post("/api/v1/iii-collections/ingress-receipts", json=receipt, headers=headers)
    ).status_code == 200
    assert (
        await client.post(
            "/api/v1/iii-collections/expected-key-reports", json=report, headers=headers
        )
    ).status_code == 200

    status_response = await client.get(f"{_route(scope)}/{command.id}")
    status = status_response.json()["data"]
    assert status["state"] == "cancel_requested"
    assert status["blockingStage"] == "cancellation"
    assert status["recoveryAction"] == "await_lifecycle"
    assert {reference["kind"] for reference in status["evidenceReferences"]} >= {
        "expected_key_report",
        "ingress_receipt",
    }

    outbound.state = "cancelled"
    await db_session.commit()
    cancelled = (await client.get(f"{_route(scope)}/{command.id}")).json()["data"]
    assert cancelled["state"] == "cancelled"
    assert cancelled["blockingStage"] is None
    assert cancelled["recoveryAction"] == "none"
    assert {reference["kind"] for reference in cancelled["evidenceReferences"]} >= {
        "expected_key_report",
        "ingress_receipt",
    }
