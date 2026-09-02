"""Integration tests for fleet auth (ADR-0005, closeout issue 04).

FleetAuthMiddleware guards every HTTP /api and /mcp route with a static bearer token.
These tests mutate the lru_cached Settings instance via monkeypatch.setattr —
the middleware reads ``get_settings().api_auth_token`` per request, so the
change is visible immediately and undone automatically after each test.
"""

import secrets

import pytest

from backend.config import get_settings
from backend.main import app
from backend.security.fleet_auth import FLEET_AUTH_ERROR_CODE
from backend.security.identity import (
    IdentitySettings,
    get_request_identity,
    identity_dependency,
)
from backend.security.local_auth import hash_password, initialize_password_hash

TOKEN = "fleet-test-token"


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "api_auth_token", TOKEN)


@pytest.fixture
def auth_disabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "api_auth_token", "")


# ── dev posture: no token configured ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_open_when_no_token_configured(client, auth_disabled):
    """No token configured -> /api routes answer without any Authorization header."""
    response = await client.get("/api/v1/system/config")
    assert response.status_code == 200
    assert response.json()["success"] is True


# ── token configured ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_header_is_401(client, auth_enabled):
    response = await client.get("/api/v1/system/config")
    assert response.status_code == 401
    body = response.json()
    assert body == {
        "success": False,
        "error": "Invalid or missing API token",
        "code": FLEET_AUTH_ERROR_CODE,
    }
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_wrong_token_is_401(client, auth_enabled):
    response = await client.get(
        "/api/v1/system/config", headers={"Authorization": "Bearer wrong-token"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == FLEET_AUTH_ERROR_CODE


@pytest.mark.asyncio
async def test_wrong_scheme_is_401(client, auth_enabled):
    response = await client.get(
        "/api/v1/system/config", headers={"Authorization": f"Basic {TOKEN}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_correct_token_is_200(client, auth_enabled):
    response = await client.get(
        "/api/v1/system/config", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_correct_token_on_db_backed_route(client, auth_enabled):
    """The guard sits in front of every /api route, not just /system."""
    response = await client.get("/api/v1/sources", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200

    response = await client.get("/api/v1/sources")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_mcp_endpoint_uses_same_fleet_token_boundary(client, auth_enabled):
    response = await client.post(
        "/mcp",
        headers={"Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_fleet_token_header_leaves_authorization_for_oidc(client, auth_enabled):
    app.dependency_overrides[get_request_identity] = identity_dependency(
        IdentitySettings(
            "https://id.example",
            "opencli",
            bootstrap_admin_token="bootstrap-token",
        )
    )

    response = await client.get(
        "/api/v1/auth/me",
        headers={
            "X-API-Token": TOKEN,
            "Authorization": "Bearer bootstrap-token",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "subject": "bootstrap-admin",
        "email": None,
        "name": "Bootstrap Admin",
        "username": None,
        "picture": None,
        "is_platform_admin": True,
        "auth_method": "bootstrap",
    }


# ── exemptions ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_exempt_and_leaks_only_opaque_process_identity(client, auth_enabled):
    """/health stays open for unauthenticated liveness probes (docker
    healthcheck) and therefore must expose liveness only — no version, no
    config flags (issue 04: exempt iff it leaks no deployment detail)."""
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "instance_id"}
    assert body["status"] == "ok"
    assert isinstance(body["instance_id"], str)
    assert body["instance_id"]


@pytest.mark.asyncio
async def test_local_admin_login_uses_simple_credentials(
    client, auth_enabled, monkeypatch, tmp_path
):
    state_path = tmp_path / "local-admin-password.hash"
    initial_password = f"initial-{secrets.token_hex(12)}"
    monkeypatch.setenv("LOCAL_AUTH_STATE_PATH", str(state_path))
    get_settings.cache_clear()
    initialize_password_hash(hash_password(initial_password), str(state_path))
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": initial_password},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["token_type"] == "bearer"
    assert payload["using_default_password"] is True

    identity = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert identity.status_code == 200
    assert identity.json()["data"]["auth_method"] == "local"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_local_admin_login_rejects_wrong_password(client, auth_disabled):
    wrong_password = f"wrong-{secrets.token_hex(8)}"
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": wrong_password},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_local_admin_can_change_password(client, auth_disabled, monkeypatch, tmp_path):
    new_password = f"local-{secrets.token_hex(8)}"
    monkeypatch.setenv("LOCAL_AUTH_STATE_PATH", str(tmp_path / "local-admin-password.hash"))
    initialize_password_hash(hash_password("admin"), str(tmp_path / "local-admin-password.hash"))
    get_settings.cache_clear()
    try:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        token = login.json()["data"]["access_token"]
        changed = await client.post(
            "/api/v1/auth/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "admin", "new_password": new_password},
        )
        assert changed.status_code == 200
        assert (
            await client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "admin"},
            )
        ).status_code == 401
        assert (
            await client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": new_password},
            )
        ).status_code == 200
        changed_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": new_password},
        )
        assert changed_login.json()["data"]["using_default_password"] is False
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_local_admin_password_survives_settings_reload(
    client, auth_disabled, monkeypatch, tmp_path
):
    state_path = tmp_path / "local-admin-password.hash"
    new_password = f"durable-{secrets.token_hex(8)}"
    monkeypatch.setenv("LOCAL_AUTH_STATE_PATH", str(state_path))
    initialize_password_hash(hash_password("admin"), str(state_path))
    get_settings.cache_clear()
    try:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        changed = await client.post(
            "/api/v1/auth/password",
            headers={"Authorization": f"Bearer {login.json()['data']['access_token']}"},
            json={"current_password": "admin", "new_password": new_password},
        )
        assert changed.status_code == 200
        assert state_path.is_file()

        monkeypatch.setenv("LOCAL_ADMIN_PASSWORD_HASH", "ignored-configured-fallback")
        get_settings.cache_clear()
        reloaded = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": new_password},
        )
        assert reloaded.status_code == 200
    finally:
        get_settings.cache_clear()
