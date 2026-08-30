"""Frozen delivery execution invariants independent of HTTP transport."""

from types import SimpleNamespace

import pytest

from backend.security.controlled_receiver import canonical_hash
from backend.workflow.delivery_authorization import _current_policy
from backend.workflow.delivery_execution import DeliveryExecutionConflictError, _payload, _retry_policy


def _decision(*, payload_hash: str | None = None):
    payload = {
        "schemaVersion": "delivery-claim-manifest-v1",
        "claims": [{"claimId": "claim-1", "contentHash": "a" * 64}],
        "manifestHashes": ["b" * 64],
    }
    return SimpleNamespace(
        payload_schema_version=payload["schemaVersion"],
        selected_claims=payload["claims"],
        manifest_set=[{"manifestHash": "b" * 64}],
        payload_hash=payload_hash or canonical_hash(payload),
    )


def test_execution_reconstructs_only_frozen_projection_and_hash():
    assert _payload(_decision())["claims"] == [{"claimId": "claim-1", "contentHash": "a" * 64}]


def test_execution_rejects_payload_hash_drift_before_network_io():
    with pytest.raises(DeliveryExecutionConflictError, match="payload hash"):
        _payload(_decision(payload_hash="x" * 64))


def test_execution_accepts_retry_values_only_from_the_exact_frozen_policy():
    _, snapshot, _ = _current_policy()
    assert _retry_policy(snapshot) == (30.0, 3)
    for mutation in (
        {"timeout": {}},
        {"retry": {**snapshot["retry"], "maxAttempts": 4}},
        {"retry": {**snapshot["retry"], "retryOn": []}},
    ):
        candidate = {**snapshot, **mutation}
        with pytest.raises(DeliveryExecutionConflictError, match="retry policy"):
            _retry_policy(candidate)
