"""Authenticated internal API client used by durable Celery dispatch tasks."""

import httpx

from backend.config import get_settings


def post_control_plane(path: str, payload: dict | None = None) -> dict:
    settings = get_settings()
    if not settings.api_auth_token:
        raise RuntimeError("API_AUTH_TOKEN is required for internal scheduler dispatch")
    with httpx.Client(timeout=90, trust_env=False) as client:
        response = client.post(
            settings.control_plane_url.rstrip("/") + path,
            headers={"X-API-Token": settings.api_auth_token},
            json=payload,
        )
        response.raise_for_status()
        return response.json()
