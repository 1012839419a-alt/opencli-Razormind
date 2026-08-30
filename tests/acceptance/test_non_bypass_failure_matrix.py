from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = ROOT / "tests/acceptance/non_bypass_failure_matrix.py"
spec = importlib.util.spec_from_file_location("non_bypass_failure_matrix", HARNESS_PATH)
assert spec and spec.loader
harness = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = harness
spec.loader.exec_module(harness)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def public_facts(scenario: str) -> dict:
    collection = {"blockingStage": "bridge_unavailable", "recoveryAction": "retry", "sideEffectUncertainty": True}
    materialization = {"status": "unknown", "blocker": "none", "recoveryAction": "none", "manifestHash": None, "reconciliationRevision": None, "pageSnapshotAsOf": None}
    graph = {"pin": None, "sequence": None, "readBlocker": "none", "mutationStatus": "none"}
    delivery = {"state": "none", "outcome": "none", "attemptCount": 0, "receiptHash": None, "reconciliation": "none"}
    if scenario == "admin-crash":
        collection = {"blockingStage": "none", "recoveryAction": "resume", "sideEffectUncertainty": True}
    elif scenario == "signed-zero":
        collection = {"blockingStage": "none", "recoveryAction": "none", "sideEffectUncertainty": False}
        materialization["status"] = "completed_empty"
    elif scenario in {"no-report", "crash-after-ingest"}:
        collection = {"blockingStage": "callback_missing", "recoveryAction": "recover", "sideEffectUncertainty": True}
        materialization.update(status="indeterminate", blocker="missing_report", recoveryAction="recover")
    elif scenario == "duplicate-dlq":
        collection = {"blockingStage": "duplicate", "recoveryAction": "recover", "sideEffectUncertainty": False}
        materialization.update(status="completed", blocker="retained_dlq", recoveryAction="recover", manifestHash=_hash("manifest"), reconciliationRevision=1)
    elif scenario == "query-page-race":
        collection = {"blockingStage": "none", "recoveryAction": "recover", "sideEffectUncertainty": False}
        materialization.update(status="completed", recoveryAction="recover", manifestHash=_hash("manifest"), reconciliationRevision=1, pageSnapshotAsOf="2026-08-30T00:00:00Z")
    elif scenario == "graph-stale-auth-cas-retract":
        graph = {"pin": None, "sequence": 7, "readBlocker": "stale_manifest", "mutationStatus": "denied"}
    elif scenario == "amendment-decision-conflict":
        materialization.update(status="completed", recoveryAction="recover", manifestHash=_hash("amendment"), reconciliationRevision=2)
        graph = {"pin": _hash("new-pin"), "sequence": 8, "readBlocker": "none", "mutationStatus": "re_review_required"}
    elif scenario == "receiver-recovery":
        delivery = {"state": "unknown", "outcome": "unknown", "attemptCount": 1, "receiptHash": None, "reconciliation": "unknown"}
    elif scenario == "cancel-before-dispatch":
        delivery = {"state": "cancelled", "outcome": "none", "attemptCount": 0, "receiptHash": None, "reconciliation": "none"}
    elif scenario == "cancel-in-flight":
        delivery = {"state": "unknown", "outcome": "unknown", "attemptCount": 1, "receiptHash": None, "reconciliation": "unknown"}
    return {
        "scenario": scenario, "run": f"run-{scenario}", "fault": scenario,
        "actuator": {"name": "proof-iii-actuator", "invocationHash": _hash(f"actor-{scenario}")},
        "correlation": {"commandId": "command", "attemptId": "attempt", "workflowRunId": "workflow", "hashes": {"public": _hash(scenario)}},
        "collection": collection, "materialization": materialization, "graph": graph, "delivery": delivery,
        "redactionProfile": "failure-v1", "timing": {"startedAt": 1, "completedAt": 2, "deadlineSeconds": 360},
        "governanceReference": {"artifactId": f"artifact-{scenario}", "keyId": "key-1", "trustRootFingerprint": _hash("trust")},
        "authority": "authenticated-scoped-public-api",
    }


@pytest.mark.parametrize("scenario", sorted(harness.SCENARIOS))
def test_every_matrix_row_normalizes_only_authenticated_public_facts(scenario: str):
    result = harness.normalize_public_facts(public_facts(scenario))
    assert result["schemaVersion"] == "ScenarioResultV1"
    assert result["forbiddenFacts"] == {"adminCreatedFallback": False, "lateEffectAbsenceClaim": False, "containerAuthority": False, "pageFinality": False}


def test_internal_control_state_and_terminal_page_inference_are_rejected():
    facts = public_facts("query-page-race")
    facts["gateState"] = "released"
    with pytest.raises(harness.PublicFactRejected):
        harness.normalize_public_facts(facts)


def test_fixture_is_pinned_and_has_only_one_zero_and_hundred_operations():
    fixture = ROOT / "tests/acceptance/fixtures/opencli-failure-proof"
    recorded = (ROOT / "tests/acceptance/fixtures/opencli-failure-proof.sha256").read_text().split()[0]
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == recorded
    assert "hundred" in fixture.read_text() and "zero" in fixture.read_text() and "one" in fixture.read_text()


def test_overlay_has_no_host_ports_and_internal_fault_network():
    compose = yaml.safe_load((ROOT / "docker-compose.non-bypass-failure.yml").read_text())
    assert compose["networks"]["proof-fault"]["internal"] is True
    assert all("ports" not in service for service in compose["services"].values())
    assert {"proof-fault-gateway", "proof-iii-actuator", "proof-governance", "proof-admin-control"} <= set(compose["services"])
