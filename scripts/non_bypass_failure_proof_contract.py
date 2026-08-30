"""Acceptance-only, redacted ScenarioResultV1 contract for failure recovery."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = "ScenarioResultV1"
_ALLOWED = frozenset({
    "schemaVersion", "scenario", "run", "fault", "actuator", "correlation", "collection",
    "materialization", "graph", "delivery", "forbiddenFacts", "redactionProfile",
    "timing", "governance",
})
_SECRET = re.compile(r"(?:bearer|token|secret|password|credential|private|transport|proxy|gate|payload)", re.I)
_HASH = re.compile(r"^[0-9a-f]{64}$")


class FailureProofRejected(RuntimeError):
    """A non-authoritative, unsafe, or internally-derived certificate candidate."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _object(value: Any, name: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise FailureProofRejected(f"{name} must have the exact acceptance allowlist")
    return value


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise FailureProofRejected(f"{name} is not bounded")
    return value


def _hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise FailureProofRejected(f"{name} is not a SHA-256 hash")
    return value


def _redacted(value: Any, path: str = "result") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _SECRET.search(str(key)):
                raise FailureProofRejected(f"forbidden control or secret fact at {path}.{key}")
            _redacted(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _redacted(child, f"{path}[{index}]")
    elif isinstance(value, str) and ("-----BEGIN" in value or value.lower().startswith("bearer ")):
        raise FailureProofRejected(f"private material at {path}")


def validate(result: dict[str, Any], *, scenario: str | None = None) -> None:
    if not isinstance(result, dict) or set(result) != _ALLOWED:
        raise FailureProofRejected("result is not ScenarioResultV1")
    _redacted(result)
    if result["schemaVersion"] != SCHEMA_VERSION:
        raise FailureProofRejected("schema version is not accepted")
    if scenario is not None and result["scenario"] != scenario:
        raise FailureProofRejected("scenario correlation changed")
    _identifier(result["scenario"], "scenario")
    _identifier(result["run"], "run")
    _identifier(result["fault"], "fault")
    actuator = _object(result["actuator"], "actuator", {"name", "invocationHash"})
    if actuator["name"] != "proof-iii-actuator":
        raise FailureProofRejected("only the pinned proof actuator may be recorded")
    _hash(actuator["invocationHash"], "actuator.invocationHash")
    correlation = _object(result["correlation"], "correlation", {"commandId", "attemptId", "workflowRunId", "hashes"})
    for name in ("commandId", "attemptId", "workflowRunId"):
        _identifier(correlation[name], f"correlation.{name}")
    if not isinstance(correlation["hashes"], dict) or not correlation["hashes"]:
        raise FailureProofRejected("correlated immutable hashes are required")
    for name, value in correlation["hashes"].items():
        _identifier(name, "correlation.hashes key")
        _hash(value, f"correlation.hashes.{name}")
    collection = _object(result["collection"], "collection", {"blockingStage", "recoveryAction", "sideEffectUncertainty"})
    if collection["blockingStage"] not in {"bridge_unavailable", "callback_missing", "ingress_unknown", "duplicate", "cancelled", "none"}:
        raise FailureProofRejected("collection blocking stage is not normalized")
    if collection["recoveryAction"] not in {"retry", "resume", "recover", "none"}:
        raise FailureProofRejected("collection recovery action is not normalized")
    if not isinstance(collection["sideEffectUncertainty"], bool):
        raise FailureProofRejected("collection uncertainty is not explicit")
    materialization = _object(result["materialization"], "materialization", {"status", "blocker", "recoveryAction", "manifestHash", "reconciliationRevision", "pageSnapshotAsOf"})
    if materialization["status"] not in {"indeterminate", "completed_empty", "rejected", "unknown", "completed"}:
        raise FailureProofRejected("materialization status is not normalized")
    if materialization["blocker"] not in {"none", "retained_dlq", "unknown_retention", "missing_report", "stale_manifest", "retract"}:
        raise FailureProofRejected("materialization blocker is not normalized")
    if materialization["recoveryAction"] not in {"recover", "none"}:
        raise FailureProofRejected("materialization recovery action is invalid")
    if materialization["manifestHash"] is not None:
        _hash(materialization["manifestHash"], "materialization.manifestHash")
    if materialization["reconciliationRevision"] is not None and (not isinstance(materialization["reconciliationRevision"], int) or materialization["reconciliationRevision"] < 1):
        raise FailureProofRejected("materialization reconciliation revision is invalid")
    if materialization["pageSnapshotAsOf"] is not None and not isinstance(materialization["pageSnapshotAsOf"], str):
        raise FailureProofRejected("page lineage must remain a nonterminal string")
    graph = _object(result["graph"], "graph", {"pin", "sequence", "readBlocker", "mutationStatus"})
    if graph["pin"] is not None:
        _hash(graph["pin"], "graph.pin")
    if graph["sequence"] is not None and (not isinstance(graph["sequence"], int) or graph["sequence"] < 0):
        raise FailureProofRejected("graph sequence is invalid")
    if graph["readBlocker"] not in {"none", "stale_manifest", "retract", "forbidden"}:
        raise FailureProofRejected("graph read blocker is invalid")
    if graph["mutationStatus"] not in {"none", "denied", "unchanged", "re_review_required"}:
        raise FailureProofRejected("graph mutation status is invalid")
    delivery = _object(result["delivery"], "delivery", {"state", "outcome", "attemptCount", "receiptHash", "reconciliation"})
    if delivery["state"] not in {"none", "reserved", "cancelled", "unknown", "pending", "settled"}:
        raise FailureProofRejected("delivery state is invalid")
    if delivery["outcome"] not in {"none", "accepted", "rejected", "unknown"}:
        raise FailureProofRejected("delivery outcome is invalid")
    if not isinstance(delivery["attemptCount"], int) or delivery["attemptCount"] < 0:
        raise FailureProofRejected("delivery attempt count is invalid")
    if delivery["receiptHash"] is not None:
        _hash(delivery["receiptHash"], "delivery.receiptHash")
    if delivery["reconciliation"] not in {"none", "signed_accepted", "signed_rejected", "unknown"}:
        raise FailureProofRejected("delivery reconciliation is invalid")
    forbidden = _object(result["forbiddenFacts"], "forbiddenFacts", {"adminCreatedFallback", "lateEffectAbsenceClaim", "containerAuthority", "pageFinality"})
    if any(value is not False for value in forbidden.values()):
        raise FailureProofRejected("certificate asserts a forbidden fact")
    if not isinstance(result["redactionProfile"], str) or not result["redactionProfile"]:
        raise FailureProofRejected("redaction profile is missing")
    timing = _object(result["timing"], "timing", {"startedAt", "completedAt", "deadlineSeconds"})
    if not all(isinstance(timing[key], int) for key in timing) or timing["completedAt"] < timing["startedAt"] or not 0 < timing["deadlineSeconds"] <= 360:
        raise FailureProofRejected("scenario timing is invalid")
    governance = _object(result["governance"], "governance", {"artifactId", "contentHash", "keyId", "trustRootFingerprint"})
    for name in governance:
        _identifier(governance[name], f"governance.{name}")
    if governance["contentHash"] != content_hash({key: value for key, value in result.items() if key != "governance"}):
        raise FailureProofRejected("governance content hash does not bind the result")
    if collection["sideEffectUncertainty"] and forbidden["lateEffectAbsenceClaim"]:
        raise FailureProofRejected("uncertain effects cannot be certified absent")
    if delivery["attemptCount"] == 0 and delivery["state"] not in {"cancelled", "unknown", "none"}:
        raise FailureProofRejected("zero delivery attempts have no public cancellation boundary")
