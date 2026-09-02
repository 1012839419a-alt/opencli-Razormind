import secrets

import pytest

from backend.config import get_settings
from backend.security.local_auth import hash_password, initialize_password_hash


@pytest.mark.asyncio
async def test_local_admin_gets_default_workspace_membership(client, monkeypatch, tmp_path):
    state_path = tmp_path / "local-admin-password.hash"
    initial_password = f"initial-{secrets.token_hex(12)}"
    monkeypatch.setenv("LOCAL_AUTH_STATE_PATH", str(state_path))
    get_settings.cache_clear()
    initialize_password_hash(hash_password(initial_password), str(state_path))
    try:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": initial_password},
        )
        token = login.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        workspaces = await client.get("/api/v1/governance/workspaces", headers=headers)
        assert workspaces.status_code == 200
        workspace = workspaces.json()["data"][0]
        assert workspace["slug"] == "opencli-default"

        automations = await client.get(
            f"/api/v1/workspaces/{workspace['id']}/automations",
            headers=headers,
        )
        assert automations.status_code == 200
        assert automations.json()["data"] == []
    finally:
        get_settings.cache_clear()
