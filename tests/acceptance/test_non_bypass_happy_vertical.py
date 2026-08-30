from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

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
    return {
        "schemaVersion": "NonBypassHappyVerticalProofV1",
        "run": "nbv-test",
        "image": runner.PINNED_III,
        "topology": {
            "fixtureDigest": digest,
            "iiiCliPath": "/opt/iii/iii",
            "iiiUrl": "ws://proof-iii:49134",
            "relay": "three-fixed-callback-paths",
        },
        "command": {"id": command_id, "runId": "nbv-test"},
        "attempt": {"commandId": command_id},
        "lifecycleHashes": ["lifecycle:1"],
        "reportHash": "report:collector:attempt-36:1",
        "ingressReceiptHash": "receipt:receipt-36",
        "researchGraphManifestRef": {"manifestHash": "m" * 64},
        "pin": {"manifestSetHash": "p" * 64},
        "decision": {
            "decisionId": decision_id,
            "manifestSetHash": "p" * 64,
            "manifests": [{"manifestHash": "m" * 64}],
        },
        "execution": {"outcome": "accepted", "decisionId": decision_id},
        "receiverReceipt": {"receipt": "verified", "outcome": "accepted"},
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


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.__setitem__("image", "iiidev/iii:latest"),
        lambda value: value["topology"].__setitem__("fixtureDigest", "0" * 64),
        lambda value: value["topology"].__setitem__("relay", "direct-admin"),
        lambda value: value.__setitem__("researchGraphManifestRef", "replacement"),
        lambda value: value["execution"].__setitem__("final_outcome", "accepted-by-2xx"),
        lambda value: value.__setitem__("privateKey", "must-not-sign"),
    ],
)
def test_pre_sign_validation_rejects_substitutions_and_secrets(mutator):
    evidence = _evidence()
    mutator(evidence)
    with pytest.raises(runner.ProofRejected):
        runner.validate_evidence(
            evidence,
            fixture_digest=hashlib.sha256(
                (ROOT / "tests/acceptance/fixtures/opencli-proof").read_bytes()
            ).hexdigest(),
            run="nbv-test",
        )


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
    assert (
        services["proof-controlled-receiver"]["networks"]["proof-receiver"]["ipv4_address"]
        == "8.8.8.8"
    )
    assert topology["networks"]["proof-receiver"]["ipam"]["config"][0]["subnet"] == "8.8.8.0/24"
    assert set(services["proof-relay"]["networks"]) == {
        "proof-control",
        "proof-callback",
        "proof-iii",
    }
