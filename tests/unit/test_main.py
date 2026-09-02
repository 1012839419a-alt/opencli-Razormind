"""Unit tests for backend/main.py."""

from unittest.mock import patch

# ── _read_chrome_endpoints ─────────────────────────────────────────────────────


def test_read_chrome_endpoints_returns_list(tmp_path):
    """_read_chrome_endpoints parses comma-separated endpoints from .env file."""
    from backend.main import _read_chrome_endpoints

    env_file = tmp_path / ".env"
    env_file.write_text("AGENT_POOL_ENDPOINTS=http://chrome:9222,http://chrome-2:9222\n")

    with patch(
        "dotenv.dotenv_values",
        return_value={"AGENT_POOL_ENDPOINTS": "http://chrome:9222,http://chrome-2:9222"},
    ):
        result = _read_chrome_endpoints()

    assert result == ["http://chrome:9222", "http://chrome-2:9222"]


def test_read_chrome_endpoints_empty_env():
    """_read_chrome_endpoints returns empty list when AGENT_POOL_ENDPOINTS not set."""
    from backend.main import _read_chrome_endpoints

    with patch("dotenv.dotenv_values", return_value={}):
        result = _read_chrome_endpoints()

    assert result == []


def test_read_chrome_endpoints_strips_whitespace():
    """_read_chrome_endpoints strips whitespace from each endpoint."""
    from backend.main import _read_chrome_endpoints

    with patch(
        "dotenv.dotenv_values",
        return_value={"AGENT_POOL_ENDPOINTS": " http://chrome:9222 , http://chrome-2:9222 "},
    ):
        result = _read_chrome_endpoints()

    assert result == ["http://chrome:9222", "http://chrome-2:9222"]


def test_read_chrome_endpoints_handles_exception():
    """_read_chrome_endpoints returns empty list if dotenv raises."""
    from backend.main import _read_chrome_endpoints

    with patch("dotenv.dotenv_values", side_effect=ImportError("no dotenv")):
        result = _read_chrome_endpoints()

    assert result == []


def test_read_chrome_endpoints_blank_value():
    """_read_chrome_endpoints returns empty list when value is blank."""
    from backend.main import _read_chrome_endpoints

    with patch("dotenv.dotenv_values", return_value={"AGENT_POOL_ENDPOINTS": "  "}):
        result = _read_chrome_endpoints()

    assert result == []


# ── create_app ────────────────────────────────────────────────────────────────


def test_create_app_returns_fastapi_app():
    """create_app returns a FastAPI application instance."""
    from fastapi import FastAPI

    from backend.main import create_app

    created = create_app()
    assert isinstance(created, FastAPI)


def test_app_has_health_endpoint(client):
    """GET /health returns ok status."""
    import asyncio

    async def _check():
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/health")
        return response

    response = asyncio.run(_check())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["instance_id"], str)
    assert data["instance_id"]


def test_each_app_process_identity_is_stable_and_unique():
    """Health identity is stable per app instance and changes for a new one."""
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from backend.main import create_app

    first_app = create_app()
    second_app = create_app()

    async def _instance_ids():
        async with AsyncClient(
            transport=ASGITransport(app=first_app), base_url="http://first"
        ) as first_client:
            first_response = await first_client.get("/health")
            repeated_response = await first_client.get("/health")
        async with AsyncClient(
            transport=ASGITransport(app=second_app), base_url="http://second"
        ) as second_client:
            second_response = await second_client.get("/health")
        return (
            first_response.json()["instance_id"],
            repeated_response.json()["instance_id"],
            second_response.json()["instance_id"],
        )

    first_id, repeated_id, second_id = asyncio.run(_instance_ids())
    assert repeated_id == first_id
    assert second_id != first_id


def test_app_has_openapi_docs():
    """GET /openapi.json returns OpenAPI schema."""
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async def _check():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.get("/openapi.json")

    response = asyncio.run(_check())
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema
    assert schema["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "description": "Operator-provisioned OpenCLI Admin API token.",
    }
    assert schema["paths"]["/api/v1/workflows/capabilities"]["get"]["security"] == [
        {"BearerAuth": []}
    ]
    assert schema["x-opencli-agent"]["mcp"]["url"] == "/mcp"


def test_root_discovers_agent_interfaces(client):
    """GET / gives a new Agent the authentication and workflow entry sequence."""
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async def _check():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.get("/")

    response = asyncio.run(_check())
    assert response.status_code == 200
    data = response.json()
    assert data["interfaces"]["mcp"]["url"] == "/mcp"
    assert data["authentication"]["scheme"] == "bearer"
    assert data["agentWorkflow"][:3] == [
        "discover capabilities",
        "arrange a review-only node draft",
        "compile and preflight",
    ]
