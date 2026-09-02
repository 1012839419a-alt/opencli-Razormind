"""Authentication dependency for scheduler/worker calls into API-owned runtime paths."""

import hmac

from fastapi import Header, HTTPException, status

from backend.config import get_settings


def require_internal_service_token(
    x_api_token: str | None = Header(default=None, alias="X-API-Token"),
) -> None:
    configured = get_settings().api_auth_token
    if not configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Internal service token is not configured",
        )
    if not x_api_token or not hmac.compare_digest(x_api_token, configured):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid internal service token")
