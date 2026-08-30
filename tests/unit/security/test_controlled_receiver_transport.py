"""Controlled receiver v2 authentication and registry security contracts."""

import json

import pytest

from backend.config import get_settings
from backend.security import controlled_receiver as receiver


@pytest.fixture(autouse=True)
def controlled_receiver_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "controlled_receiver_registry_json", json.dumps({
        "receiver-primary": {
            "url": "https://receiver.example/deliver",
            "receiverIdentity": "receiver-a",
            "credentialReference": "credential-a",
            "requestKeyId": "request-a",
            "receiptKeyId": "receipt-a",
            "allowedNetworks": ["93.184.216.0/24"],
        }
    }))
    monkeypatch.setattr(settings, "controlled_receiver_credentials_json", json.dumps({"credential-a": "request-secret"}))
    monkeypatch.setattr(settings, "controlled_receiver_inbound_keys_json", json.dumps({"request-a": "request-secret"}))
    monkeypatch.setattr(settings, "controlled_receiver_receipt_keys_json", json.dumps({"receipt-a": "receipt-secret"}))
    monkeypatch.setattr(settings, "controlled_receiver_max_clock_skew_seconds", 300)


def _body():
    return receiver.canonical_json({
        "version": "v2", "receiverIdentity": "receiver-a", "operationId": "op-1",
        "decisionHash": "d" * 64, "payloadHash": "p" * 64, "payload": {"schemaVersion": "delivery-claim-manifest-v1"},
    })


def test_registry_requires_server_identity_and_fixed_scope():
    endpoint = receiver.resolve_endpoint("receiver-primary", "credential-a")
    assert endpoint.url == "https://receiver.example/deliver"
    with pytest.raises(receiver.ControlledReceiverSecurityError):
        receiver.resolve_endpoint("receiver-primary", "client-supplied-credential")


def test_request_mac_binds_canonical_body_and_identity():
    endpoint = receiver.resolve_endpoint("receiver-primary", "credential-a")
    body = _body()
    headers = receiver.request_headers(body=body, endpoint=endpoint, operation_id="op-1", decision_hash="d" * 64, payload_hash="p" * 64)
    assert receiver.verify_request(body=body, headers=headers, receiver_identity="receiver-a", operation_id="op-1", decision_hash="d" * 64, payload_hash="p" * 64) == ("request-a", headers["X-Controlled-Receiver-Nonce"])
    with pytest.raises(receiver.ControlledReceiverSecurityError):
        receiver.verify_request(body=body + b" ", headers=headers, receiver_identity="receiver-a", operation_id="op-1", decision_hash="d" * 64, payload_hash="p" * 64)


def test_signed_receipt_alone_controls_rejected_outcome():
    endpoint = receiver.resolve_endpoint("receiver-primary", "credential-a")
    payload = receiver.receipt_payload(receiver_identity="receiver-a", operation_id="op-1", decision_hash="d" * 64, payload_hash="p" * 64, durable_status="rejected", receipt_id="receipt-1", issued_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    receipt = {**payload, "keyId": "receipt-a", "signature": receiver.sign_receipt(payload, "receipt-a")}
    assert receiver.verify_receipt(receipt=receipt, endpoint=endpoint, operation_id="op-1", decision_hash="d" * 64, payload_hash="p" * 64) == "rejected"
    receipt["signature"] = "tampered"
    with pytest.raises(receiver.ControlledReceiverSecurityError):
        receiver.verify_receipt(receipt=receipt, endpoint=endpoint, operation_id="op-1", decision_hash="d" * 64, payload_hash="p" * 64)
