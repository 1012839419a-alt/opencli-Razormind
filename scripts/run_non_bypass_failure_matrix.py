#!/usr/bin/env python3
"""Run failure scenarios only when their real public-boundary facts are present.

The runner is deliberately unable to mint a result from Compose state, actuator
responses, or gate state. A scenario is signed only after the in-network driver
has written an authenticated scoped-public-API fact document.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from scripts.run_non_bypass_happy_vertical import (
    RunLedger as HappyRunLedger,
    _make_identities,
    _make_secrets,
)

from scripts.non_bypass_failure_proof_contract import canonical, content_hash, validate
from scripts.proof_bundle_governance import Principal, ProofBundleStore
from tests.acceptance.non_bypass_failure_matrix import SCENARIO_ORDER, SCENARIOS, normalize_public_facts

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/acceptance/fixtures/opencli-failure-proof"
FIXTURE_DIGEST = ROOT / "tests/acceptance/fixtures/opencli-failure-proof.sha256"
PINNED_III = "iiidev/iii:0.19.4@sha256:14ed48b463d8a2e0d3583512acf106b3514f406c5e9965a5854710ff936e1e86"


class FailureRunRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class ScenarioLedger:
    scenario: str
    project: str
    scratch: Path
    artifact: Path


def _run(command: list[str], *, env: dict[str, str], input: str | None = None, timeout: int = 360) -> str:
    try:
        completed = subprocess.run(command, cwd=ROOT, env=env, input=input, text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise FailureRunRejected(f"command timed out: {' '.join(command)}") from exc
    if completed.returncode:
        raise FailureRunRejected(completed.stderr.strip() or completed.stdout.strip() or "command failed")
    return completed.stdout


def _fixture_digest() -> str:
    expected = FIXTURE_DIGEST.read_text("utf-8").split()[0]
    actual = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    if actual != expected:
        raise FailureRunRejected("failure fixture digest is not pinned")
    return actual


def _compose(ledger: ScenarioLedger, env: dict[str, str], base: Path, overlay: Path, *args: str, input: str | None = None, timeout: int = 360) -> str:
    return _run(["docker", "compose", "-p", ledger.project, "-f", str(base), "-f", str(overlay), *args], env=env, input=input, timeout=timeout)



def _configure_failure_receiver(ledger: ScenarioLedger, values: dict[str, str]) -> None:
    """Bind the failure-only public-class receiver without touching #36's base."""
    ip = os.environ.get("PROOF_RECEIVER_IP", "1.1.1.1")
    subnet = os.environ.get("PROOF_RECEIVER_SUBNET", "1.1.1.0/24")
    credentials = json.loads(values["CONTROLLED_RECEIVER_CREDENTIALS_JSON"])
    inbound = json.loads(values["CONTROLLED_RECEIVER_INBOUND_KEYS_JSON"])
    receipts = json.loads(values["CONTROLLED_RECEIVER_RECEIPT_KEYS_JSON"])
    credential_reference, request_key = next(iter(credentials.items()))
    request_key_id = next(iter(inbound))
    receipt_key_id = next(iter(receipts))
    values["CONTROLLED_RECEIVER_REGISTRY_JSON"] = json.dumps({
        "receiver-channel-proof": {
            "url": f"https://{ip}:8000/api/v1/controlled-receiver/v2/deliver",
            "receiverIdentity": "controlled-receiver-proof",
            "credentialReference": credential_reference,
            "requestKeyId": request_key_id,
            "receiptKeyId": receipt_key_id,
            "allowedNetworks": [subnet],
            "durableStatus": "accepted",
        }
    }, sort_keys=True, separators=(",", ":"))
    (ledger.scratch / "controlled_receiver_registry_json").write_text(values["CONTROLLED_RECEIVER_REGISTRY_JSON"], encoding="utf-8")
    os.chmod(ledger.scratch / "controlled_receiver_registry_json", 0o600)
    (ledger.scratch / "receiver.ext").write_text(
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        f"subjectAltName=DNS:proof-controlled-receiver,IP:{ip}\n",
        encoding="utf-8",
    )
    _run([
        "openssl", "x509", "-req", "-days", "1", "-in", str(ledger.scratch / "receiver.csr"),
        "-CA", str(ledger.scratch / "ca.pem"), "-CAkey", str(ledger.scratch / "ca-key.pem"),
        "-CAcreateserial", "-extfile", str(ledger.scratch / "receiver.ext"),
        "-out", str(ledger.scratch / "receiver-cert.pem"),
    ], env={**os.environ})
def _admit(ledger: ScenarioLedger, env: dict[str, str], base: Path, overlay: Path) -> dict[str, Any]:
    """Build one scenario-private catalog, then admit it before `up --no-build`."""
    digest = _fixture_digest()
    _compose(ledger, env, base, overlay, "config", "--quiet", timeout=120)
    _compose(ledger, env, base, overlay, "build", "--pull", timeout=1200)
    images = _compose(ledger, env, base, overlay, "config", "--images", timeout=120).splitlines()
    if PINNED_III not in images:
        raise FailureRunRejected("pinned III catalog image is absent")
    image_ids = {
        image: _run(["docker", "image", "inspect", "--format", "{{.Id}}", image], env=env, timeout=120).strip()
        for image in images
    }
    if any(not image_id.startswith("sha256:") for image_id in image_ids.values()):
        raise FailureRunRejected("catalog image identity is not immutable")
    report = {
        "scenario": ledger.scenario,
        "fixtureDigest": digest,
        "catalogImageIds": image_ids,
        "project": ledger.project,
    }
    # Admission report is intentionally unsigned and never becomes a bundle fact.
    ledger.artifact.mkdir(parents=True, exist_ok=True)
    (ledger.artifact / "admission.json").write_bytes(canonical(report))
    return report


def _facts_from_driver(ledger: ScenarioLedger, env: dict[str, str], base: Path, overlay: Path) -> dict[str, Any]:
    if ledger.scenario not in {"admin-crash", "iii-unreachable", "no-report", "signed-zero"}:
        raise FailureRunRejected(f"in-network driver is not implemented for {ledger.scenario}")
    command = [
        "docker", "compose", "-p", ledger.project, "-f", str(base), "-f", str(overlay),
        "exec", "-T", "proof-driver", "python", "tests/acceptance/non_bypass_failure_driver.py",
        "--scenario", ledger.scenario, "--run", ledger.project,
    ]
    process = subprocess.Popen(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if ledger.scenario == "signed-zero":
        stdout, stderr = process.communicate(timeout=120)
        if process.returncode:
            diagnostic = _compose(
                ledger, env, base, overlay, "exec", "-T", "proof-driver", "curl", "-fsS",
                "-H", f"X-API-Token: {env['API_AUTH_TOKEN']}",
                "http://proof-relay:8080/_gate/report-diagnostics", timeout=30,
            )
            collector_log = _compose(
                ledger, env, base, overlay, "logs", "--tail", "80", "proof-collector", timeout=30,
            )
            raise FailureRunRejected(
                (stderr.strip() or stdout.strip() or "signed-zero driver failed")
                + f"; relay report diagnostic: {diagnostic}; collector diagnostic: {collector_log}"
            )
        return normalize_public_facts(json.loads(stdout))
    signal_name = "iii-ready" if ledger.scenario == "iii-unreachable" else "submitted"
    signal = ledger.artifact / "coordination" / f"{ledger.project}.{signal_name}"
    deadline = time.monotonic() + 90
    while not signal.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    if not signal.exists():
        process.kill()
        _stdout, stderr = process.communicate(timeout=30)
        raise FailureRunRejected(
            f"{ledger.scenario} driver did not reach its public gate boundary: "
            + (stderr.strip() or _stdout.strip() or "no driver output")
        )
    if ledger.scenario == "admin-crash":
        _compose(ledger, env, base, overlay, "kill", "proof-admin", timeout=30)
        _compose(
            ledger, env, base, overlay, "exec", "-T", "proof-driver", "curl", "-fsS",
            "-X", "POST", "-H", f"X-API-Token: {env['API_AUTH_TOKEN']}",
            "-H", "Content-Type: application/json", "-d", '{"upstream":"control"}',
            "http://proof-relay:8080/_gate/callback-upstream", timeout=30,
        )
        release_name = "resume"
    elif ledger.scenario == "no-report":
        _compose(
            ledger, env, base, overlay, "exec", "-T", "proof-driver", "curl", "-fsS",
            "-X", "POST", "-H", f"X-API-Token: {env['API_AUTH_TOKEN']}",
            "-H", "Content-Type: application/json", "-d", '{"mode":"drop"}',
            "http://proof-relay:8080/_gate/report", timeout=30,
        )
        release_name = "resume"
    else:
        _run(
            ["docker", "network", "disconnect", f"{ledger.project}_proof-iii-admin", f"{ledger.project}-proof-admin-1"],
            env=env,
            timeout=30,
        )
        release_name = "iii-release"
    (ledger.artifact / "coordination" / f"{ledger.project}.{release_name}").write_text(
        "released", encoding="utf-8"
    )
    stdout, stderr = process.communicate(timeout=120)
    if process.returncode:
        raise FailureRunRejected(stderr.strip() or stdout.strip() or "in-network admin-crash driver failed")
    try:
        facts = json.loads(stdout)
        return normalize_public_facts(facts)
    except (json.JSONDecodeError, RuntimeError) as exc:
        raise FailureRunRejected(
            f"in-network driver facts failed normalization: {exc}"
        ) from exc


def _govern(ledger: ScenarioLedger, result: dict[str, Any], now: int) -> dict[str, Any]:
    scope = {"workspace": "failure", "project": ledger.project, "workflow": "failure-matrix", "run": result["run"]}
    # The durable store contains only redacted records/audit data. The generated
    # audit private key is process-only scratch material and is never written.
    root = ledger.artifact / "g"
    store = ProofBundleStore(root, audit_private_key=Ed25519PrivateKey.generate(), now=lambda: now)
    admin, writer = Principal("key-admin", "key-admin", scope), Principal("bundle-writer", "bundle-writer", scope)
    key = store.bootstrap_active(admin, key_id="failure-active-v1", not_before=now - 1, not_after=now + 86400)
    artifact_id = f"{ledger.scenario[:8]}-{uuid.uuid4().hex[:12]}"
    result["governance"] = {"artifactId": artifact_id, "contentHash": content_hash({key: value for key, value in result.items() if key != "governance"}), "keyId": key.key_id, "trustRootFingerprint": store.trust_root_fingerprint}
    validate(result, scenario=ledger.scenario)
    envelope = {
        "governanceSchemaVersion": "ProofBundleGovernanceV1", "artifactId": artifact_id, "scenarioId": ledger.scenario,
        "run": result["run"], "contentHash": content_hash(result), "sourceSchemaVersion": "ScenarioResultV1",
        "createdAt": now, "expiresAt": now + 86400, "retentionClass": "release-proof", "retentionPolicyVersion": "v1",
        "scope": scope, "redactionProfile": result["redactionProfile"], "signatureAlgorithm": "Ed25519", "keyId": key.key_id,
    }
    saved = store.create(writer, artifact_id=artifact_id, payload=result, envelope=envelope)
    store.verify(writer, artifact_id=artifact_id)
    return saved


def _cleanup(ledger: ScenarioLedger, env: dict[str, str], base: Path, overlay: Path) -> None:
    try:
        _compose(ledger, env, base, overlay, "down", "--volumes", "--remove-orphans", timeout=60)
    finally:
        shutil.rmtree(ledger.scratch, ignore_errors=True)

def run_matrix(artifact_dir: Path, *, compose_file: Path, overlay_file: Path) -> list[Path]:
    results: list[Path] = []
    for scenario in SCENARIO_ORDER:
        run_id = f"nbf-{scenario}-{uuid.uuid4().hex[:12]}"
        ledger = ScenarioLedger(scenario, run_id, Path(tempfile.mkdtemp(prefix=f"{run_id}-")), artifact_dir / scenario)
        os.chmod(ledger.scratch, 0o700)
        ledger.artifact.mkdir(mode=0o700, parents=True, exist_ok=True)
        base_ledger = HappyRunLedger(run_id, ledger.project, ledger.scratch, ledger.artifact)
        values = _make_secrets(base_ledger)
        _configure_failure_receiver(ledger, values)
        _make_identities(base_ledger, values)
        env = {
            **os.environ,
            **values,
            "PROOF_SCENARIO": scenario,
            "PROOF_SECRETS_DIR": str(ledger.scratch),
            "PROOF_ARTIFACT_DIR": str(ledger.artifact),
            "PROOF_FIXTURE_DIGEST": _fixture_digest(),
            "COMPOSE_PARALLEL_LIMIT": "1",
        }
        started = time.monotonic()
        try:
            _admit(ledger, env, compose_file, overlay_file)
            _compose(ledger, env, compose_file, overlay_file, "up", "--detach", "--no-build", timeout=120)
            result = _facts_from_driver(ledger, env, compose_file, overlay_file)
            if time.monotonic() - started > 360:
                raise FailureRunRejected("scenario exceeded the 360 second bound")
            saved = _govern(ledger, result, int(time.time()))
            path = ledger.artifact / "proof.json"
            path.write_bytes(canonical(saved))
            results.append(path)
        finally:
            _cleanup(ledger, env, compose_file, overlay_file)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose-file", type=Path, default=ROOT / "docker-compose.non-bypass-acceptance.yml")
    parser.add_argument("--overlay-file", type=Path, default=ROOT / "docker-compose.non-bypass-failure.yml")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run_matrix(args.artifact_dir, compose_file=args.compose_file, overlay_file=args.overlay_file)
    except FailureRunRejected as exc:
        print(f"failure matrix rejected: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
