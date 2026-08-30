"""Integration contracts for the separately authenticated durable receiver surface."""

import json

import pytest
from httpx import AsyncClient

from backend.config import get_settings
from backend.security import controlled_receiver as receiver


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
async def test_receiver_v2_mac_exemption_does_not_accept_invalid_mac_or_oversized_body(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_auth_token", "fleet-token")
    value = _request()
    body = receiver.canonical_json(value)
    endpoint = receiver.resolve_endpoint("receiver-primary", "credential-a")
    headers = receiver.request_headers(body=body, endpoint=endpoint, operation_id=value["operationId"], decision_hash=value["decisionHash"], payload_hash=value["payloadHash"])
    headers["X-Controlled-Receiver-Mac"] = "invalid"
    assert (await client.post("/api/v1/controlled-receiver/v2/deliver", content=body, headers=headers)).status_code == 401
    assert (await client.post("/api/v1/controlled-receiver/v2/deliver", content=b"x" * (64 * 1024 + 1), headers={"Content-Type": "application/json"})).status_code == 413