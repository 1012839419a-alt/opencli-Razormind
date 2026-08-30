"""Container entry point for the internal proof-governance HTTP service."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import Request
from jose import jwt

from scripts.proof_bundle_governance import GovernanceDenied, Principal, ProofBundleStore, create_app


def _authenticate(request: Request) -> Principal:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise GovernanceDenied("credential is missing", 401)
    token = authorization[7:]
    try:
        jwks = json.loads(os.environ["PROOF_GOVERNANCE_JWKS"])
        header = jwt.get_unverified_header(token)
        key = next(item for item in jwks["keys"] if item.get("kid") == header.get("kid"))
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=os.environ.get("PROOF_GOVERNANCE_AUDIENCE", "proof-governance"),
            issuer=os.environ.get("PROOF_GOVERNANCE_ISSUER", "http://proof-oidc"),
        )
        role = claims["role"]
        scope = claims["proof_scope"]
        if role not in {"bundle-writer", "key-admin"} or not isinstance(scope, dict):
            raise ValueError("invalid role or scope")
        scope = {str(key): str(value) for key, value in scope.items()}
        if set(scope) != {"workspace", "project", "workflow", "run"}:
            raise ValueError("invalid scope")
        return Principal(str(claims["sub"]), role, scope)
    except Exception as exc:
        raise GovernanceDenied("credential is invalid", 401) from exc


store = ProofBundleStore(Path(os.environ.get("PROOF_GOVERNANCE_ROOT", "/tmp/proof-governance")))
app = create_app(store, _authenticate)
