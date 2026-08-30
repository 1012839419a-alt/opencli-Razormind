#!/usr/bin/env python3
"""Fail-closed durable governance for redacted acceptance proof bundles.

This module is intentionally a release-harness service, not an Admin API.  It
keeps signing material outside the artifact store and exposes only public
fingerprints and signed redacted metadata through its HTTP adapter.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import Depends, FastAPI, HTTPException, Request

SCHEMA_VERSION = "ProofBundleGovernanceV1"
BUNDLE_SCHEMA = "ScenarioResultV1"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SECRET = re.compile(r"(?:bearer|token|secret|password|credential|private|transport|receiver.*key)", re.I)
ENVELOPE_FIELDS = frozenset({
    "governanceSchemaVersion", "artifactId", "scenarioId", "run", "contentHash",
    "sourceSchemaVersion", "createdAt", "expiresAt", "retentionClass",
    "retentionPolicyVersion", "scope", "redactionProfile", "signatureAlgorithm", "keyId",
})
AUDIT_FIELDS = frozenset({
    "auditSchemaVersion", "id", "at", "actor", "action", "artifactId", "contentHash",
    "scopeHash", "outcome", "reason", "previousHash", "keyId", "signature",
})


class GovernanceDenied(RuntimeError):
    """An invalid governance operation which issued no certificate."""

    def __init__(self, reason: str, status_code: int = 403) -> None:
        super().__init__(reason)
        self.status_code = status_code


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    scope: Mapping[str, str]


@dataclass(frozen=True)
class SigningKey:
    key_id: str
    public_key: str
    not_before: int
    not_after: int
    revoked_at: int | None = None
    retired_at: int | None = None


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def fingerprint(public_key: bytes) -> str:
    return hashlib.sha256(public_key).hexdigest()


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise GovernanceDenied("invalid encoded public material", 422) from exc


def _public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def _assert_redacted(value: Any, path: str = "bundle") -> None:
    if isinstance(value, dict):
        for name, child in value.items():
            if _SECRET.search(str(name)):
                raise GovernanceDenied(f"secret-bearing field is forbidden at {path}.{name}", 422)
            _assert_redacted(child, f"{path}.{name}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_redacted(child, f"{path}[{index}]")
    elif isinstance(value, str) and ("-----BEGIN" in value or value.lower().startswith("bearer ")):
        raise GovernanceDenied(f"private material is forbidden at {path}", 422)


class ProofBundleStore:
    """Append-only audit and immutable bundle store, scoped per scenario."""

    def __init__(self, root: Path, *, audit_private_key: Ed25519PrivateKey | None = None, now: Callable[[], int] | None = None) -> None:
        self.root = root
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._now = now or (lambda: int(time.time()))
        self._audit_private = audit_private_key or Ed25519PrivateKey.generate()
        self._audit_public = _public_bytes(self._audit_private)
        self._audit_key_id = f"audit-root-{fingerprint(self._audit_public)[:16]}"
        self._key_private: dict[str, Ed25519PrivateKey] = {}
        self._keys: dict[str, SigningKey] = {}
        self._active_key: str | None = None

    @property
    def trust_root_fingerprint(self) -> str:
        return fingerprint(self._audit_public)

    def trust_root(self) -> dict[str, str]:
        return {"keyId": self._audit_key_id, "fingerprint": self.trust_root_fingerprint, "algorithm": "Ed25519"}

    def _scope_hash(self, scope: Mapping[str, str]) -> str:
        return digest(dict(sorted(scope.items())))

    def _scope_dir(self, scope: Mapping[str, str]) -> Path:
        path = self.root / self._scope_hash(scope)
        path.mkdir(mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)
        return path

    def _audit_path(self, scope: Mapping[str, str]) -> Path:
        return self._scope_dir(scope) / "audit.jsonl"

    def _records(self, scope: Mapping[str, str]) -> list[dict[str, Any]]:
        path = self._audit_path(scope)
        if not path.exists():
            return []
        try:
            return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]
        except (OSError, json.JSONDecodeError) as exc:
            raise GovernanceDenied("audit continuity is unreadable", 409) from exc

    def _append_audit(self, principal: Principal, action: str, *, artifact_id: str | None = None, content_hash: str | None = None, outcome: str = "allowed", reason: str | None = None) -> dict[str, Any]:
        _assert_redacted({"action": action, "artifactId": artifact_id, "contentHash": content_hash, "reason": reason})
        previous = self._records(principal.scope)
        predecessor = digest(previous[-1]) if previous else "0" * 64
        unsigned = {
            "auditSchemaVersion": SCHEMA_VERSION, "id": uuid.uuid4().hex, "at": self._now(),
            "actor": principal.subject, "action": action, "artifactId": artifact_id,
            "contentHash": content_hash, "scopeHash": self._scope_hash(principal.scope),
            "outcome": outcome, "reason": reason, "previousHash": predecessor, "keyId": self._audit_key_id,
        }
        record = {**unsigned, "signature": _b64(self._audit_private.sign(canonical(unsigned)))}
        path = self._audit_path(principal.scope)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        os.chmod(path, 0o600)
        return record

    def _deny(self, principal: Principal | None, action: str, reason: str, status: int = 403) -> None:
        if principal is not None:
            self._append_audit(principal, action, outcome="denied", reason=reason)
        raise GovernanceDenied(reason, status)

    def _require_role(self, principal: Principal, role: str, action: str) -> None:
        if principal.role != role:
            self._deny(principal, action, "role is not authorized")

    def _bundle_dir(self, scope: Mapping[str, str], artifact_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", artifact_id):
            raise GovernanceDenied("artifact id is invalid", 422)
        return self._scope_dir(scope) / "bundles" / artifact_id

    def _key_for_signing(self) -> SigningKey:
        if self._active_key is None:
            raise GovernanceDenied("no active bundle key", 409)
        key = self._keys[self._active_key]
        now = self._now()
        if key.revoked_at is not None or not (key.not_before <= now < key.not_after):
            raise GovernanceDenied("active bundle key is unusable", 409)
        return key

    def bootstrap_active(self, principal: Principal, *, key_id: str, not_before: int, not_after: int) -> SigningKey:
        self._require_role(principal, "key-admin", "key.bootstrap-active")
        if self._active_key is not None or key_id in self._keys or not_before >= not_after:
            self._deny(principal, "key.bootstrap-active", "invalid immutable active-key bootstrap", 409)
        private = Ed25519PrivateKey.generate()
        key = SigningKey(key_id, _b64(_public_bytes(private)), not_before, not_after)
        self._keys[key_id], self._key_private[key_id], self._active_key = key, private, key_id
        self._append_audit(principal, "key.bootstrap-active")
        return key

    def stage_next(self, principal: Principal, *, key_id: str, not_before: int, not_after: int) -> SigningKey:
        self._require_role(principal, "key-admin", "key.stage-next")
        if key_id in self._keys or not_before >= not_after:
            self._deny(principal, "key.stage-next", "invalid staged key", 409)
        private = Ed25519PrivateKey.generate()
        key = SigningKey(key_id, _b64(_public_bytes(private)), not_before, not_after)
        self._keys[key_id], self._key_private[key_id] = key, private
        self._append_audit(principal, "key.stage-next")
        return key

    def promote(self, principal: Principal, *, key_id: str) -> SigningKey:
        self._require_role(principal, "key-admin", "key.promote")
        candidate = self._keys.get(key_id)
        if candidate is None or candidate.revoked_at is not None or not (candidate.not_before <= self._now() < candidate.not_after):
            self._deny(principal, "key.promote", "staged key is not active-eligible", 409)
        self._active_key = key_id
        self._append_audit(principal, "key.promote")
        return candidate

    def retire(self, principal: Principal, *, key_id: str) -> SigningKey:
        self._require_role(principal, "key-admin", "key.retire")
        key = self._keys.get(key_id)
        if key is None or key.revoked_at is not None:
            self._deny(principal, "key.retire", "key cannot be retired", 409)
        retired = SigningKey(**{**asdict(key), "retired_at": self._now()})
        self._keys[key_id] = retired
        if self._active_key == key_id:
            self._active_key = None
        self._append_audit(principal, "key.retire")
        return retired

    def revoke(self, principal: Principal, *, key_id: str) -> SigningKey:
        self._require_role(principal, "key-admin", "key.revoke")
        key = self._keys.get(key_id)
        if key is None or key.revoked_at is not None:
            self._deny(principal, "key.revoke", "key cannot be revoked", 409)
        now = self._now()
        revoked = SigningKey(**{**asdict(key), "revoked_at": now, "retired_at": now})
        self._keys[key_id] = revoked
        self._key_private.pop(key_id, None)
        if self._active_key == key_id:
            self._active_key = None
        self._append_audit(principal, "key.revoke")
        return revoked

    def _key_public(self, key_id: str) -> Ed25519PublicKey:
        key = self._keys.get(key_id)
        if key is None:
            raise GovernanceDenied("unknown bundle key", 409)
        return Ed25519PublicKey.from_public_bytes(_unb64(key.public_key))

    def create(self, principal: Principal, *, artifact_id: str, payload: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
        self._require_role(principal, "bundle-writer", "bundle.create")
        _assert_redacted(payload)
        if not isinstance(payload, dict) or payload.get("schemaVersion") != BUNDLE_SCHEMA:
            self._deny(principal, "bundle.create", "only ScenarioResultV1 may be certified", 422)
        if set(envelope) != ENVELOPE_FIELDS:
            self._deny(principal, "bundle.create", "envelope is not the immutable allowlist", 422)
        _assert_redacted(envelope)
        content_hash, now = digest(payload), self._now()
        if envelope["governanceSchemaVersion"] != SCHEMA_VERSION or envelope["artifactId"] != artifact_id:
            self._deny(principal, "bundle.create", "envelope identity is invalid", 422)
        if envelope["contentHash"] != content_hash or envelope["sourceSchemaVersion"] != BUNDLE_SCHEMA:
            self._deny(principal, "bundle.create", "canonical content hash is invalid", 422)
        if envelope["scope"] != dict(principal.scope) or envelope["createdAt"] != now:
            self._deny(principal, "bundle.create", "scope or creation time is invalid", 422)
        if not isinstance(envelope["expiresAt"], int) or envelope["expiresAt"] <= now:
            self._deny(principal, "bundle.create", "certificate is already expired", 422)
        key = self._key_for_signing()
        if envelope["signatureAlgorithm"] != "Ed25519" or envelope["keyId"] != key.key_id:
            self._deny(principal, "bundle.create", "envelope key is not active", 422)
        if envelope["expiresAt"] > key.not_after:
            self._deny(principal, "bundle.create", "bundle validity exceeds signing-key validity", 422)
        target, record = self._bundle_dir(principal.scope, artifact_id), {"envelope": envelope, "payload": payload}
        if target.exists():
            try:
                existing = json.loads((target / "record.json").read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                self._deny(principal, "bundle.create", "immutable record is unreadable", 409)
            if canonical(existing["record"]) != canonical(record):
                self._deny(principal, "bundle.create", "artifact id already has different bytes", 409)
            self._append_audit(principal, "bundle.create", artifact_id=artifact_id, content_hash=content_hash)
            return existing
        signature = _b64(self._key_private[key.key_id].sign(canonical(record)))
        target.mkdir(mode=0o700, parents=True)
        saved = {"record": record, "signature": signature}
        (target / "record.json").write_bytes(canonical(saved))
        os.chmod(target / "record.json", 0o600)
        self._append_audit(principal, "bundle.create", artifact_id=artifact_id, content_hash=content_hash)
        return saved

    def _expire(self, principal: Principal, target: Path, artifact_id: str, saved: dict[str, Any]) -> None:
        metadata = saved["record"]["envelope"]
        tombstone = {key: metadata[key] for key in ("contentHash", "keyId", "retentionClass", "retentionPolicyVersion", "expiresAt")}
        tombstone["artifactId"] = artifact_id
        (target / "tombstone.json").write_bytes(canonical(tombstone))
        os.chmod(target / "tombstone.json", 0o600)
        (target / "record.json").unlink(missing_ok=True)
        self._append_audit(principal, "bundle.tombstone", artifact_id=artifact_id, content_hash=tombstone["contentHash"])

    def _load(self, principal: Principal, artifact_id: str) -> tuple[Path, dict[str, Any]]:
        target = self._bundle_dir(principal.scope, artifact_id)
        if (target / "tombstone.json").exists():
            self._deny(principal, "bundle.read", "bundle has expired", 410)
        try:
            saved = json.loads((target / "record.json").read_text("utf-8"))
        except FileNotFoundError:
            self._deny(principal, "bundle.read", "bundle was not found", 404)
        except (OSError, json.JSONDecodeError):
            self._deny(principal, "bundle.read", "bundle bytes are invalid", 409)
        envelope = saved.get("record", {}).get("envelope", {})
        if not isinstance(envelope, dict) or envelope.get("expiresAt", 0) <= self._now():
            self._expire(principal, target, artifact_id, saved)
            self._deny(principal, "bundle.read", "bundle has expired", 410)
        return target, saved

    def read(self, principal: Principal, *, artifact_id: str) -> dict[str, Any]:
        _, saved = self._load(principal, artifact_id)
        self._append_audit(principal, "bundle.read", artifact_id=artifact_id, content_hash=saved["record"]["envelope"]["contentHash"])
        return saved

    def verify(self, principal: Principal, *, artifact_id: str) -> dict[str, Any]:
        _, saved = self._load(principal, artifact_id)
        record, signature = saved.get("record"), saved.get("signature")
        try:
            envelope = record["envelope"]
            key = self._keys[envelope["keyId"]]
            if (
                key.revoked_at is not None
                or not (key.not_before <= envelope["createdAt"] < key.not_after)
                or envelope["expiresAt"] > key.not_after
            ):
                raise GovernanceDenied("bundle key lifecycle rejects verification", 409)
            self._key_public(key.key_id).verify(_unb64(signature), canonical(record))
        except (KeyError, TypeError, InvalidSignature, GovernanceDenied):
            self._deny(principal, "bundle.verify", "bundle signature is invalid", 409)
        self._append_audit(principal, "bundle.verify", artifact_id=artifact_id, content_hash=envelope["contentHash"])
        return {"verified": True, "artifactId": artifact_id, "contentHash": envelope["contentHash"], "keyId": key.key_id}

    def read_audit(self, principal: Principal) -> list[dict[str, Any]]:
        self._append_audit(principal, "audit.read")
        records, predecessor = self._records(principal.scope), "0" * 64
        for record in records:
            if set(record) != AUDIT_FIELDS or record["previousHash"] != predecessor or record["keyId"] != self._audit_key_id:
                self._deny(principal, "audit.read", "audit continuity is invalid", 409)
            unsigned = {key: value for key, value in record.items() if key != "signature"}
            try:
                self._audit_private.public_key().verify(_unb64(record["signature"]), canonical(unsigned))
            except (InvalidSignature, GovernanceDenied):
                self._deny(principal, "audit.read", "audit signature is invalid", 409)
            predecessor = digest(record)
        return records


def create_app(store: ProofBundleStore, authenticate: Callable[[Request], Principal]) -> FastAPI:
    """Create a no-port HTTP surface; the host supplies local-OIDC authentication."""
    app = FastAPI(title="proof-governance", docs_url=None, redoc_url=None, openapi_url=None)

    def principal(request: Request) -> Principal:
        try:
            return authenticate(request)
        except GovernanceDenied as exc:
            raise HTTPException(exc.status_code, detail="authentication denied") from exc

    def invoke(action: Callable[[], Any]) -> Any:
        try:
            return action()
        except GovernanceDenied as exc:
            raise HTTPException(exc.status_code, detail=str(exc)) from exc

    @app.get("/v1/trust-root")
    def trust_root(actor: Principal = Depends(principal)) -> Any:
        return invoke(store.trust_root)

    @app.post("/v1/bundles")
    async def create_bundle(request: Request, actor: Principal = Depends(principal)) -> Any:
        body = await request.json()
        return invoke(lambda: store.create(actor, artifact_id=body.get("artifactId", ""), payload=body.get("payload"), envelope=body.get("envelope")))

    @app.get("/v1/bundles/{artifact_id}")
    def read_bundle(artifact_id: str, actor: Principal = Depends(principal)) -> Any:
        return invoke(lambda: store.read(actor, artifact_id=artifact_id))

    @app.post("/v1/bundles/{artifact_id}/verify")
    def verify_bundle(artifact_id: str, actor: Principal = Depends(principal)) -> Any:
        return invoke(lambda: store.verify(actor, artifact_id=artifact_id))

    @app.get("/v1/audit")
    def audit(actor: Principal = Depends(principal)) -> Any:
        return invoke(lambda: store.read_audit(actor))

    for route, method in (("bootstrap-active", "bootstrap_active"), ("stage-next", "stage_next"), ("promote", "promote"), ("retire", "retire"), ("revoke", "revoke")):
        async def key_operation(request: Request, actor: Principal = Depends(principal), _method: str = method) -> Any:
            body = await request.json()
            return invoke(lambda: asdict(getattr(store, _method)(actor, **body)))
        app.post(f"/v1/keys/{route}")(key_operation)
    return app


def temporary_store(*, now: Callable[[], int] | None = None) -> ProofBundleStore:
    """Test helper: production runners pass a 0700 scenario directory explicitly."""
    return ProofBundleStore(Path(tempfile.mkdtemp(prefix="proof-governance-")), now=now)
