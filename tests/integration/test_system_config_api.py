import pytest

from backend.config import get_settings


@pytest.mark.asyncio
async def test_system_config_exposes_runtime_sections(client):
    response = await client.get("/api/v1/system/config")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["collection_mode"] == "local"
    assert "agent_pool_endpoints" in data
    assert "credential_encryption_configured" in data
    assert "effective_cdp_endpoints" in data
    assert data["effective_cdp_endpoints"] == (
        data["agent_pool_endpoints"]
        if data["agent_pool_endpoints"]
        else [data["opencli_cdp_endpoint"]]
    )
    assert "control_kill_switch" in data


@pytest.mark.asyncio
async def test_system_config_updates_safe_runtime_fields(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ENV_FILE_PATH", str(tmp_path / ".env"))
    monkeypatch.setenv("AGENT_POOL_ENDPOINTS", "")
    get_settings.cache_clear()
    try:
        response = await client.patch(
            "/api/v1/system/config",
            json={
                "collection_mode": "agent",
                "local_max_concurrent_pipelines": 12,
                "default_timezone": "Asia/Shanghai",
                "control_kill_switch": True,
                "agent_pool_endpoints": "http://agent-1:19222, http://agent-2:19222",
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["collection_mode"] == "agent"
        assert data["local_max_concurrent_pipelines"] == 12
        assert data["default_timezone"] == "Asia/Shanghai"
        assert data["control_kill_switch"] is True
        assert data["agent_pool_endpoints"] == [
            "http://agent-1:19222",
            "http://agent-2:19222",
        ]
        assert data["effective_cdp_endpoints"] == data["agent_pool_endpoints"]
    finally:
        get_settings.cache_clear()
