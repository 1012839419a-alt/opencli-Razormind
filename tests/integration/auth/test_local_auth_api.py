import pytest
import pytest_asyncio
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import get_settings
from backend.security import local_auth
from backend.security.identity import OIDCVerifier, RequestIdentity

FLEET_TOKEN = "fleet-test-token"
BOOTSTRAP_TOKEN = "bootstrap-test-token"
CLAIM_CODE = "01ARZ3NDEK"


@pytest_asyncio.fixture
async def appliance_auth(monkeypatch, db_engine):
    settings = get_settings()
    monkeypatch.setattr(settings, "api_auth_token", FLEET_TOKEN)
    monkeypatch.setattr(settings, "bootstrap_admin_token", BOOTSTRAP_TOKEN)
    monkeypatch.setattr(settings, "device_claim_code", CLAIM_CODE)
    monkeypatch.setattr(settings, "oidc_issuer", "")
    monkeypatch.setattr(settings, "oidc_audience", "")
    monkeypatch.setattr(settings, "oidc_jwks_url", "")
    monkeypatch.setattr(settings, "local_session_cookie_secure", False)
    session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr(local_auth, "local_auth_session_factory", session_factory)
    yield settings


def _setup_body(**overrides):
    body = {
        "claim_code": CLAIM_CODE,
        "username": "owner",
        "display_name": "设备管理员",
        "password": "correct horse battery staple",
        "remember_device": False,
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_status_exposes_missing_claim_for_upgrade_recovery(
    client,
    appliance_auth,
    monkeypatch,
):
    monkeypatch.setattr(appliance_auth, "device_claim_code", "")
    status_response = await client.get("/api/v1/auth/status")
    assert status_response.status_code == 200
    assert status_response.json()["data"]["initialized"] is False
    assert status_response.json()["data"]["claim_available"] is False


@pytest.mark.asyncio
async def test_status_setup_session_csrf_logout_flow(
    client,
    db_session,
    appliance_auth,
):
    status_response = await client.get("/api/v1/auth/status")
    assert status_response.status_code == 200
    assert status_response.json()["data"] == {
        "initialized": False,
        "claim_available": True,
        "oidc_enabled": False,
        "local_login_enabled": False,
        "recovery_enabled": True,
    }

    setup_response = await client.post("/api/v1/auth/setup", json=_setup_body())
    assert setup_response.status_code == 201
    assert setup_response.json()["data"] == {
        "subject": "local:owner",
        "email": None,
        "name": "设备管理员",
        "username": "owner",
        "picture": None,
        "is_platform_admin": True,
        "auth_method": "local",
    }
    cookie = setup_response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "; secure" not in cookie
    assert "max-age" not in cookie
    assert "opencli_session" not in setup_response.text
    issued_session_token = setup_response.cookies.get(local_auth.SESSION_COOKIE_NAME)
    assert issued_session_token
    await db_session.commit()

    me_response = await client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["data"]["auth_method"] == "local"

    second_setup = await client.post(
        "/api/v1/auth/setup",
        json=_setup_body(username="second"),
    )
    assert second_setup.status_code == 409

    no_csrf = await client.post("/api/v1/auth/logout")
    assert no_csrf.status_code == 403
    assert no_csrf.json() == {"success": False, "error": "CSRF header required"}

    logout = await client.post(
        "/api/v1/auth/logout",
        headers={"X-OpenCLI-CSRF": "1"},
    )
    assert logout.status_code == 200
    assert logout.json()["data"] == {"signed_out": True}
    await db_session.commit()

    after_logout = await client.get("/api/v1/auth/me")
    assert after_logout.status_code == 401
    replay_after_logout = await client.get(
        "/api/v1/auth/me",
        headers={
            "Cookie": f"{local_auth.SESSION_COOKIE_NAME}={issued_session_token}",
        },
    )
    assert replay_after_logout.status_code == 401


@pytest.mark.asyncio
async def test_secure_cookie_override_applies_to_set_and_delete_behind_proxy(
    client,
    db_session,
    appliance_auth,
    monkeypatch,
):
    monkeypatch.setattr(appliance_auth, "local_session_cookie_secure", True)

    setup_response = await client.post("/api/v1/auth/setup", json=_setup_body())
    assert setup_response.status_code == 201
    set_cookie = setup_response.headers["set-cookie"].lower()
    assert "; secure" in set_cookie
    session_token = setup_response.cookies.get(local_auth.SESSION_COOKIE_NAME)
    assert session_token
    await db_session.commit()

    # The test backend is HTTP, matching TLS termination at a reverse proxy.
    # Send the secure cookie explicitly because an HTTPX jar correctly refuses
    # to attach Secure cookies to the internal HTTP request on its own.
    logout_response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Cookie": f"{local_auth.SESSION_COOKIE_NAME}={session_token}",
            "X-OpenCLI-CSRF": "1",
        },
    )
    assert logout_response.status_code == 200
    delete_cookie = logout_response.headers["set-cookie"].lower()
    assert "; secure" in delete_cookie
    assert "max-age=0" in delete_cookie


@pytest.mark.asyncio
async def test_login_has_uniform_failure_and_local_cookie_never_authenticates_mcp(
    client,
    db_session,
    appliance_auth,
):
    setup_response = await client.post("/api/v1/auth/setup", json=_setup_body())
    assert setup_response.status_code == 201
    await db_session.commit()
    client.cookies.clear()

    wrong_password = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "owner",
            "password": "wrong password",
            "remember_device": True,
        },
    )
    missing_user = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "nobody",
            "password": "wrong password",
            "remember_device": True,
        },
    )
    assert wrong_password.status_code == missing_user.status_code == 401
    assert wrong_password.json() == missing_user.json() == {
        "detail": "Invalid username or password"
    }

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "owner",
            "password": "correct horse battery staple",
            "remember_device": True,
        },
    )
    assert login.status_code == 200
    assert "max-age=" in login.headers["set-cookie"].lower()
    immediate_me = await client.get("/api/v1/auth/me")
    assert immediate_me.status_code == 200
    assert immediate_me.json()["data"]["auth_method"] == "local"
    await db_session.commit()

    mcp = await client.post(
        "/mcp",
        headers={"Content-Type": "application/json", "X-OpenCLI-CSRF": "1"},
        json={"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
    )
    assert mcp.status_code == 401


@pytest.mark.asyncio
async def test_bootstrap_bearer_crosses_fleet_barrier_without_fleet_header(
    client,
    appliance_auth,
):
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {BOOTSTRAP_TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["auth_method"] == "bootstrap"
    assert response.json()["data"]["is_platform_admin"] is True


@pytest.mark.asyncio
async def test_verified_oidc_bearer_is_human_http_auth_and_is_written_to_scope(
    client,
    appliance_auth,
    monkeypatch,
):
    settings = appliance_auth
    monkeypatch.setattr(settings, "oidc_issuer", "https://id.example")
    monkeypatch.setattr(settings, "oidc_audience", "opencli")

    async def fake_verify(self, token):
        if token != "valid-oidc-token":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid bearer token")
        return RequestIdentity(
            subject="oidc-user",
            email="owner@example.com",
            name="OIDC User",
            username="oidc-user",
        )

    monkeypatch.setattr(OIDCVerifier, "verify", fake_verify)

    config_response = await client.get(
        "/api/v1/system/config",
        headers={"Authorization": "Bearer valid-oidc-token"},
    )
    assert config_response.status_code == 200

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer valid-oidc-token"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["data"]["subject"] == "oidc-user"
    assert me_response.json()["data"]["auth_method"] == "oidc"

    invalid_response = await client.get(
        "/api/v1/system/config",
        headers={"Authorization": "Bearer invalid-oidc-token"},
    )
    assert invalid_response.status_code == 401
