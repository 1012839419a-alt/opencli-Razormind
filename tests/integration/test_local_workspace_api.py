import pytest


@pytest.mark.asyncio
async def test_local_admin_gets_default_workspace_membership(client):
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"},
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
