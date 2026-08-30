"""Strict redacted DTO contract for the isolated non-bypass proof."""

from __future__ import annotations

import json
import re
from typing import Any

PINNED_III = "iiidev/iii:0.19.4@sha256:14ed48b463d8a2e0d3583512acf106b3514f406c5e9965a5854710ff936e1e86"
ALLOWED_BUNDLE_KEYS = frozenset({
    "schemaVersion", "run", "image", "topology", "command", "attempt",
    "lifecycleHashes", "reportHash", "ingressReceiptHash",
    "researchGraphManifestRef", "pin", "decision", "execution",
    "receiverReceipt", "redactionProfile",
})
_SECRET_NAME = re.compile(r"(?:secret|token|password|credential|private|key)", re.I)
_SAFE_NAMES = frozenset({"expectedRecordKeySetHash", "keyId", "nonSecretConfigHash", "excludedItemKeys"})
_HASH = re.compile(r"^[0-9a-f]{64}$")


class ProofRejected(RuntimeError):
    """A non-authoritative, substituted, or unsafe proof input was rejected."""


def _object(value: Any, name: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ProofRejected(f"{name} does not have the exact redacted DTO shape")
    return value


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProofRejected(f"{name} is not a non-empty identifier")
    return value


def _hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ProofRejected(f"{name} is not an immutable SHA-256 hash")
    return value


def _assert_no_secrets(value: Any, path: str = "bundle") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key not in _SAFE_NAMES and _SECRET_NAME.search(str(key)):
                raise ProofRejected(f"secret-bearing field is forbidden at {path}.{key}")
            _assert_no_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_secrets(child, f"{path}[{index}]")
    elif isinstance(value, str) and "-----BEGIN" in value:
        raise ProofRejected(f"private transport material is forbidden at {path}")


def validate_evidence(evidence: dict[str, Any], *, fixture_digest: str, run: str) -> None:
    if not isinstance(evidence, dict) or set(evidence) != ALLOWED_BUNDLE_KEYS:
        raise ProofRejected("proof bundle keys are not the acceptance allowlist")
    _assert_no_secrets(evidence)
    if evidence["schemaVersion"] != "NonBypassHappyVerticalProofV1" or evidence["run"] != run or evidence["image"] != PINNED_III:
        raise ProofRejected("proof identity or pinned engine changed")
    topology = _object(evidence["topology"], "topology", {"fixtureDigest", "iiiCliPath", "iiiUrl", "relay"})
    if _hash(topology["fixtureDigest"], "topology.fixtureDigest") != fixture_digest:
        raise ProofRejected("fixture digest was substituted")
    if topology["iiiCliPath"] != "/opt/iii/iii" or topology["iiiUrl"] != "ws://proof-iii:49134" or topology["relay"] != "three-fixed-callback-paths":
        raise ProofRejected("III admission facts are missing or bypassed")
    command = _object(evidence["command"], "command", {"id", "workflowRunId", "payloadHash"})
    command_id = _identifier(command["id"], "command.id")
    if _identifier(command["workflowRunId"], "command.workflowRunId") == run:
        raise ProofRejected("proof run was used as the workflow run")
    _hash(command["payloadHash"], "command.payloadHash")
    attempt = _object(evidence["attempt"], "attempt", {"id", "commandId", "attemptNumber"})
    if _identifier(attempt["id"], "attempt.id") is None or attempt["commandId"] != command_id or not isinstance(attempt["attemptNumber"], int) or attempt["attemptNumber"] < 1:
        raise ProofRejected("command/attempt correlation failed")
    lifecycle = _object(evidence["lifecycleHashes"], "lifecycleHashes", {"bridgeAccepted", "collectorStarted", "collectorReturned"})
    for name, value in lifecycle.items(): _hash(value, f"lifecycleHashes.{name}")
    report_hash, ingress_hash = _hash(evidence["reportHash"], "reportHash"), _hash(evidence["ingressReceiptHash"], "ingressReceiptHash")
    if len({*lifecycle.values(), report_hash, ingress_hash}) != 5:
        raise ProofRejected("vertical evidence hashes are not distinct immutable facts")
    manifest = _object(evidence["researchGraphManifestRef"], "researchGraphManifestRef", {"batchId", "derivation", "reconciliationRevision", "manifestSchemaVersion", "manifestHash", "expectedRecordKeySetHash", "recordRefSetHash", "materializationStatus"})
    if _identifier(manifest["batchId"], "manifest.batchId") is None or manifest["derivation"] != "dispatch-task-v1" or manifest["manifestSchemaVersion"] != "v1" or manifest["materializationStatus"] != "completed" or not isinstance(manifest["reconciliationRevision"], int) or manifest["reconciliationRevision"] < 1:
        raise ProofRejected("materialized manifest is not a completed canonical reference")
    for name in ("manifestHash", "expectedRecordKeySetHash", "recordRefSetHash"): _hash(manifest[name], f"manifest.{name}")
    pin = _object(evidence["pin"], "pin", {"sequence", "researchRevisionId", "manifestSetHash"})
    if not isinstance(pin["sequence"], int) or pin["sequence"] < 1: raise ProofRejected("pin.sequence is invalid")
    _identifier(pin["researchRevisionId"], "pin.researchRevisionId")
    pin_hash = _hash(pin["manifestSetHash"], "pin.manifestSetHash")
    decision = _object(evidence["decision"], "decision", {"operationId", "decisionId", "decisionHash", "payloadHash", "manifestSetHash", "manifests"})
    operation_id, decision_id = _identifier(decision["operationId"], "decision.operationId"), _identifier(decision["decisionId"], "decision.decisionId")
    decision_hash, decision_payload = _hash(decision["decisionHash"], "decision.decisionHash"), _hash(decision["payloadHash"], "decision.payloadHash")
    if _hash(decision["manifestSetHash"], "decision.manifestSetHash") != pin_hash: raise ProofRejected("frozen decision is not bound to the pinned graph")
    if not isinstance(decision["manifests"], list) or not decision["manifests"]: raise ProofRejected("decision manifests are absent")
    manifest_hashes = {_hash(_object(item, "decision.manifests[]", {"manifestHash"})["manifestHash"], "decision.manifests[].manifestHash") for item in decision["manifests"]}
    if manifest["manifestHash"] not in manifest_hashes: raise ProofRejected("decision does not retain the materialized manifest")
    execution = _object(evidence["execution"], "execution", {"executionId", "operationId", "decisionId", "decisionHash", "payloadHash", "outcome", "attemptCount"})
    if _identifier(execution["executionId"], "execution.executionId") is None or execution["operationId"] != operation_id or execution["decisionId"] != decision_id or _hash(execution["decisionHash"], "execution.decisionHash") != decision_hash or _hash(execution["payloadHash"], "execution.payloadHash") != decision_payload or execution["outcome"] != "accepted" or not isinstance(execution["attemptCount"], int) or execution["attemptCount"] < 1:
        raise ProofRejected("delivery execution is not terminally accepted and frozen")
    receipt = _object(evidence["receiverReceipt"], "receiverReceipt", {"attemptNumber", "receiptId", "receiptHash", "receipt", "outcome"})
    if not isinstance(receipt["attemptNumber"], int) or receipt["attemptNumber"] < 1 or not _identifier(receipt["receiptId"], "receiverReceipt.receiptId") or receipt["receipt"] != "verified" or receipt["outcome"] != "accepted": raise ProofRejected("verified receiver receipt is absent")
    _hash(receipt["receiptHash"], "receiverReceipt.receiptHash")
    if not isinstance(evidence["redactionProfile"], str) or not evidence["redactionProfile"]: raise ProofRejected("redaction profile is absent")


def assert_substitutions_rejected(evidence: dict[str, Any], *, fixture_digest: str, run: str) -> None:
    substitutions = (("engine", lambda p: p.__setitem__("image", "iiidev/iii:latest")), ("fixture", lambda p: p["topology"].__setitem__("fixtureDigest", "0" * 64)), ("relay", lambda p: p["topology"].__setitem__("relay", "direct-admin")), ("manifest", lambda p: p.__setitem__("researchGraphManifestRef", "replacement")), ("terminal", lambda p: p["execution"].__setitem__("final_outcome", "accepted-by-2xx")))
    for name, mutate in substitutions:
        candidate = json.loads(json.dumps(evidence)); mutate(candidate)
        try: validate_evidence(candidate, fixture_digest=fixture_digest, run=run)
        except ProofRejected: continue
        raise AssertionError(f"unsafe {name} substitution reached signing")
