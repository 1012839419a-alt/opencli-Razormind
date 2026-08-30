from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from scripts.non_bypass_proof_contract import source_binding_hash

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/run_non_bypass_happy_vertical.py"
spec = importlib.util.spec_from_file_location("non_bypass_runner", RUNNER_PATH)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


def _evidence() -> dict:
    digest = hashlib.sha256(
        (ROOT / "tests/acceptance/fixtures/opencli-proof").read_bytes()
    ).hexdigest()
    command_id = "command-36"
    decision_id = "decision-36"
    payload_hash = "a" * 64
    manifest_hash = "b" * 64
    pin_hash = "c" * 64
    workflow_id = "workflow-36"
    workflow_run_id = "workflow-run-36"
    task_id = "task-36"
    batch_id = str(
        uuid5(
            NAMESPACE_URL,
            f"opencli-admin/workflow/{workflow_id}/run/{workflow_run_id}/batch/{task_id}",
        )
    )
    lifecycle_hashes = {
        "bridgeAccepted": "1" * 64,
        "collectorStarted": "2" * 64,
        "collectorReturned": "3" * 64,
    }
    report_hash = "4" * 64
    ingress_hash = "5" * 64
    operation_id = "delivery-nbv-test-{}".format(
        source_binding_hash(
            run="nbv-test",
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
            command_id=command_id,
            attempt_id="attempt-36",
            attempt_number=1,
            task_id=task_id,
            payload_hash=payload_hash,
            batch_id=batch_id,
            manifest_hash=manifest_hash,
            lifecycle_hashes=lifecycle_hashes,
            report_hash=report_hash,
            ingress_receipt_hash=ingress_hash,
        )
    )
    return {
        "schemaVersion": "NonBypassHappyVerticalProofV1",
        "run": "nbv-test",
        "image": runner.PINNED_III,
        "topology": {
            "fixtureDigest": digest,
            "iiiCliPath": "/opt/iii/iii",
            "iiiUrl": "ws://proof-iii:49134",
            "relay": "three-fixed-callback-paths",
            "containerTransport": "docker-internal",
            "callbackRoute": "relay-only",
            "receiverEndpoint": "https://8.8.8.8:8000",
            "receiverExposure": "internal-only",
            "receiverKind": "controlled-receiver-v2",
        },
        "command": {
            "id": command_id,
            "workflowId": workflow_id,
            "workflowRunId": workflow_run_id,
            "payloadHash": payload_hash,
        },
        "attempt": {
            "id": "attempt-36",
            "commandId": command_id,
            "attemptNumber": 1,
            "taskId": task_id,
        },
        "lifecycleHashes": lifecycle_hashes,
        "reportHash": report_hash,
        "ingressReceiptHash": ingress_hash,
        "researchGraphManifestRef": {
            "batchId": batch_id,
            "derivation": "dispatch-task-v1",
            "reconciliationRevision": 1,
            "manifestSchemaVersion": "v1",
            "manifestHash": manifest_hash,
            "expectedRecordKeySetHash": "6" * 64,
            "recordRefSetHash": "7" * 64,
            "materializationStatus": "completed",
            "materializationAuthority": "scoped-admin-api",
            "sourceCorrelation": {
                "workflowRunId": workflow_run_id,
                "commandId": command_id,
                "attemptId": "attempt-36",
                "payloadHash": payload_hash,
                "batchId": batch_id,
                "manifestHash": manifest_hash,
                "reportHash": report_hash,
                "ingressReceiptHash": ingress_hash,
                "lifecycleHashes": lifecycle_hashes,
            },
        },
        "pin": {"sequence": 3, "researchRevisionId": "research-36", "manifestSetHash": pin_hash},
        "decision": {
            "operationId": operation_id,
            "decisionId": decision_id,
            "decisionHash": "8" * 64,
            "payloadHash": "0" * 64,
            "manifestSetHash": pin_hash,
            "manifests": [{"manifestHash": manifest_hash}],
        },
        "execution": {
            "executionId": "execution-36",
            "operationId": operation_id,
            "decisionId": decision_id,
            "decisionHash": "8" * 64,
            "payloadHash": "0" * 64,
            "outcome": "accepted",
            "attemptCount": 1,
        },
        "receiverReceipt": {
            "attemptNumber": 1,
            "receiptId": "receiver-receipt-36",
            "receiptHash": "9" * 64,
            "httpStatus": 200,
            "receipt": "verified",
            "durableReceipt": "verified",
            "outcome": "accepted",
        },
        "redactionProfile": "non-bypass-happy-v1",
    }


def test_fixture_is_committed_and_supports_only_canonical_calls(tmp_path: Path):
    fixture = ROOT / "tests/acceptance/fixtures/opencli-proof"
    expected = (ROOT / "tests/acceptance/fixtures/opencli-proof.sha256").read_text().split()[0]
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == expected
    help_result = subprocess.run(
        ["sh", str(fixture), "bilibili", "search", "--help"], capture_output=True, text=True
    )
    assert help_result.returncode == 0
    result = subprocess.run(
        ["sh", str(fixture), "bilibili", "search", "--keyword", "vertical-proof", "-f", "json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0 and json_item(result.stdout)["bvid"] == "BV1verticalproof"
    assert subprocess.run(["sh", str(fixture), "x", "y"], capture_output=True).returncode != 0


def json_item(raw: str) -> dict:
    import json

    return json.loads(raw)[0]


def test_pre_sign_validation_accepts_only_correlated_terminal_facts():
    evidence = _evidence()
    runner.validate_evidence(
        evidence, fixture_digest=evidence["topology"]["fixtureDigest"], run="nbv-test"
    )


def test_rejects_command_payload_spliced_from_another_evidence_chain():
    evidence = _evidence()
    evidence["command"]["payloadHash"] = "d" * 64
    _assert_rejected(evidence)


def test_rejects_collection_chain_spliced_into_the_original_delivery_chain():
    evidence = _evidence()
    workflow_id = "workflow-other"
    workflow_run_id = "workflow-run-other"
    task_id = "task-other"
    batch_id = str(
        uuid5(
            NAMESPACE_URL,
            f"opencli-admin/workflow/{workflow_id}/run/{workflow_run_id}/batch/{task_id}",
        )
    )
    lifecycle_hashes = {
        "bridgeAccepted": "a" * 64,
        "collectorStarted": "b" * 64,
        "collectorReturned": "c" * 64,
    }
    evidence["command"].update(
        id="command-other", workflowId=workflow_id, workflowRunId=workflow_run_id
    )
    evidence["attempt"].update(id="attempt-other", commandId="command-other", taskId=task_id)
    evidence["researchGraphManifestRef"].update(batchId=batch_id)
    evidence["lifecycleHashes"] = lifecycle_hashes
    evidence["reportHash"] = "e" * 64
    evidence["ingressReceiptHash"] = "f" * 64
    evidence["researchGraphManifestRef"]["sourceCorrelation"] = {
        "workflowRunId": workflow_run_id,
        "commandId": "command-other",
        "attemptId": "attempt-other",
        "payloadHash": evidence["command"]["payloadHash"],
        "batchId": batch_id,
        "manifestHash": evidence["researchGraphManifestRef"]["manifestHash"],
        "reportHash": "e" * 64,
        "ingressReceiptHash": "f" * 64,
        "lifecycleHashes": lifecycle_hashes,
    }
    _assert_rejected(evidence)


def _assert_rejected(evidence: dict) -> None:
    with pytest.raises(runner.ProofRejected):
        runner.validate_evidence(
            evidence,
            fixture_digest=hashlib.sha256(
                (ROOT / "tests/acceptance/fixtures/opencli-proof").read_bytes()
            ).hexdigest(),
            run="nbv-test",
        )


def test_pinned_engine_and_fixture_invariants_reject_replacements():
    engine = _evidence()
    engine["image"] = "iiidev/iii:latest"
    _assert_rejected(engine)
    fixture = _evidence()
    fixture["topology"]["fixtureDigest"] = "0" * 64
    _assert_rejected(fixture)


def test_rejects_mock_transport_provenance_candidate():
    evidence = _evidence()
    evidence["topology"]["containerTransport"] = "mock"
    _assert_rejected(evidence)


def test_rejects_public_webhook_receiver_provenance_candidate():
    evidence = _evidence()
    evidence["topology"]["receiverEndpoint"] = "https://public-webhook.invalid"
    evidence["topology"]["receiverExposure"] = "public"
    _assert_rejected(evidence)


def test_rejects_projection_only_manifest_provenance_candidate():
    evidence = _evidence()
    evidence["researchGraphManifestRef"]["materializationAuthority"] = "projection-only"
    _assert_rejected(evidence)


def test_rejects_direct_admin_fallback_provenance_candidate():
    evidence = _evidence()
    evidence["topology"]["callbackRoute"] = "direct-admin"
    _assert_rejected(evidence)


def test_rejects_bare_http_2xx_without_verified_durable_receipt_candidate():
    evidence = _evidence()
    assert evidence["receiverReceipt"]["httpStatus"] == 200
    evidence["receiverReceipt"]["durableReceipt"] = "missing"
    _assert_rejected(evidence)


def test_rejects_stale_receiver_receipt_attempt():
    evidence = _evidence()
    evidence["execution"]["attemptCount"] = 2
    assert evidence["receiverReceipt"]["attemptNumber"] == 1
    _assert_rejected(evidence)


def test_rejects_mismatched_receiver_receipt_attempt():
    evidence = _evidence()
    evidence["receiverReceipt"]["attemptNumber"] = 2
    _assert_rejected(evidence)


def test_mandatory_substitution_audit_is_itself_fail_closed():
    evidence = _evidence()
    runner.assert_substitutions_rejected(
        evidence, fixture_digest=evidence["topology"]["fixtureDigest"], run="nbv-test"
    )


def test_compose_topology_is_isolated_and_has_the_required_proof_networks():
    import yaml

    topology = yaml.safe_load((ROOT / "docker-compose.non-bypass-acceptance.yml").read_text())
    services = topology["services"]
    assert not any("ports" in service for service in services.values())
    assert services["proof-iii"]["image"] == runner.PINNED_III
    assert services["proof-admin"]["networks"] == [
        "proof-control",
        "proof-query",
        "proof-callback",
        "proof-receiver",
        "proof-iii-admin",
    ]
    assert services["proof-collector"]["networks"] == ["proof-iii-worker"]
    assert services["proof-bridge"]["networks"] == ["proof-iii-worker", "proof-odp"]
    assert services["proof-relay"]["networks"] == [
        "proof-control",
        "proof-callback",
        "proof-iii-worker",
    ]
    assert (
        services["proof-controlled-receiver"]["networks"]["proof-receiver"]["ipv4_address"]
        == "8.8.8.8"
    )
    assert topology["networks"]["proof-receiver"]["ipam"]["config"][0]["subnet"] == "8.8.8.0/24"
    for name in (
        "proof-admin-postgres",
        "proof-odp-postgres",
        "proof-receiver-postgres",
        "proof-redis",
        "proof-relay",
        "proof-oidc",
    ):
        assert "@sha256:" in services[name]["image"]
        assert services[name]["platform"] == "linux/amd64"


def test_live_runner_writes_a_verifiable_artifact_and_removes_labeled_resources(tmp_path: Path):
    artifact = runner.run(tmp_path / "proofs")
    proof = artifact / "proof.json"
    signature = base64.b64decode((artifact / "proof.json.sig").read_text())
    public = Ed25519PublicKey.from_public_bytes(
        base64.b64decode((artifact / "proof.pub").read_text())
    )
    public.verify(signature, proof.read_bytes().rstrip(b"\n"))
    evidence = json.loads(proof.read_text())
    runner.validate_evidence(
        evidence,
        fixture_digest=evidence["topology"]["fixtureDigest"],
        run=evidence["run"],
    )
    assert not artifact.with_name(f".{artifact.name}.partial").exists()
    for command in (
        ["docker", "ps", "-aq"],
        ["docker", "network", "ls", "-q"],
        ["docker", "volume", "ls", "-q"],
    ):
        result = subprocess.run(
            [*command, "--filter", f"label=com.docker.compose.project={artifact.name}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0
        assert not result.stdout.strip()
