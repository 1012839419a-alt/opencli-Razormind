from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/proof_bundle_governance.py"
spec = importlib.util.spec_from_file_location("proof_bundle_governance", MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _hash(seed: str) -> str:
    import hashlib
    return hashlib.sha256(seed.encode()).hexdigest()


def _result() -> dict:
    return {
        "schemaVersion": "ScenarioResultV1", "scenario": "iii-unreachable", "run": "run-1", "fault": "disconnect",
        "correlation": {"commandId": "command-1", "attemptId": "attempt-1", "workflowRunId": "workflow-run-1", "hashes": {"command": _hash("command")}},
        "collection": {"blockingStage": "bridge_unavailable", "recoveryAction": "retry", "sideEffectUncertainty": True},
        "materialization": {"status": "unknown", "blocker": "none", "recoveryAction": "none", "manifestHash": None, "reconciliationRevision": None, "pageSnapshotAsOf": None},
        "graph": {"pin": None, "sequence": None, "readBlocker": "none", "mutationStatus": "none"},
        "delivery": {"state": "none", "outcome": "none", "attemptCount": 0, "receiptHash": None, "reconciliation": "none"},
        "forbiddenFacts": {"adminCreatedFallback": False, "lateEffectAbsenceClaim": False, "containerAuthority": False, "pageFinality": False},
        "redactionProfile": "failure-v1",
        "timing": {"startedAt": 100, "completedAt": 101, "deadlineSeconds": 360},
    }


def _store(tmp_path: Path, clock: list[int]):
    store = module.ProofBundleStore(tmp_path, now=lambda: clock[0])
    scope = {"workspace": "w", "project": "p", "workflow": "f", "run": "r"}
    admin = module.Principal("admin", "key-admin", scope)
    writer = module.Principal("writer", "bundle-writer", scope)
    store.bootstrap_active(admin, key_id="k1", not_before=1, not_after=1000)
    return store, admin, writer


def _envelope(store, writer, result, now: int, expires: int = 200) -> dict:
    return {
        "governanceSchemaVersion": module.SCHEMA_VERSION, "artifactId": "artifact-1", "scenarioId": result["scenario"], "run": result["run"],
        "contentHash": module.digest(result), "sourceSchemaVersion": "ScenarioResultV1", "createdAt": now, "expiresAt": expires,
        "retentionClass": "failure", "retentionPolicyVersion": "v1", "scope": dict(writer.scope), "redactionProfile": "failure-v1",
        "signatureAlgorithm": "Ed25519", "keyId": "k1",
    }


def test_signed_immutable_bundle_and_audit_chain(tmp_path: Path):
    clock = [100]
    store, _admin, writer = _store(tmp_path, clock)
    result = _result()
    saved = store.create(writer, artifact_id="artifact-1", payload=result, envelope=_envelope(store, writer, result, 100))
    assert saved["record"]["envelope"]["contentHash"] == module.digest(result)
    assert store.verify(writer, artifact_id="artifact-1")["verified"] is True
    assert store.read(writer, artifact_id="artifact-1") == saved
    records = store.read_audit(writer)
    assert {record["action"] for record in records} >= {"bundle.create", "bundle.verify", "bundle.read", "audit.read"}
    changed = _result()
    changed["fault"] = "changed"
    with pytest.raises(module.GovernanceDenied):
        store.create(writer, artifact_id="artifact-1", payload=changed, envelope=_envelope(store, writer, changed, 100))


def test_writer_cannot_administer_keys_and_denial_is_audited(tmp_path: Path):
    clock = [100]
    store, _admin, writer = _store(tmp_path, clock)
    with pytest.raises(module.GovernanceDenied):
        store.stage_next(writer, key_id="k2", not_before=101, not_after=1000)
    assert store.read_audit(writer)[-2]["outcome"] == "denied"


def test_tamper_and_expiry_fail_closed_without_certificate(tmp_path: Path):
    clock = [100]
    store, _admin, writer = _store(tmp_path, clock)
    result = _result()
    store.create(writer, artifact_id="artifact-1", payload=result, envelope=_envelope(store, writer, result, 100, 101))
    clock[0] = 102
    with pytest.raises(module.GovernanceDenied) as expired:
        store.verify(writer, artifact_id="artifact-1")
    assert expired.value.status_code == 410
    tombstone = next(tmp_path.rglob("tombstone.json"))
    assert "contentHash" in tombstone.read_text()


def test_audit_tampering_is_detected_after_audit_read_is_recorded(tmp_path: Path):
    clock = [100]
    store, _admin, writer = _store(tmp_path, clock)
    audit = next(tmp_path.rglob("audit.jsonl"))
    audit.write_text(audit.read_text().replace('"action":"key.bootstrap-active"', '"action":"key.bootstrap-tampered"'))
    with pytest.raises(module.GovernanceDenied):
        store.read_audit(writer)


def test_secret_bearing_input_is_rejected_and_never_written(tmp_path: Path):
    clock = [100]
    store, _admin, writer = _store(tmp_path, clock)
    result = _result()
    result["privateKey"] = "not allowed"
    with pytest.raises(module.GovernanceDenied):
        store.create(writer, artifact_id="artifact-1", payload=result, envelope=_envelope(store, writer, result, 100))
    assert not list(tmp_path.rglob("record.json"))


def test_no_port_http_surface_exposes_only_authenticated_governance(tmp_path: Path):
    clock = [100]
    store, _admin, writer = _store(tmp_path, clock)
    app = module.create_app(store, lambda _request: writer)
    client = TestClient(app)
    assert client.get("/v1/trust-root").status_code == 200
    result = _result()
    response = client.post("/v1/bundles", json={
        "artifactId": "artifact-1",
        "payload": result,
        "envelope": _envelope(store, writer, result, 100),
    })
    assert response.status_code == 200
    assert client.post("/v1/bundles/artifact-1/verify").json()["verified"] is True
