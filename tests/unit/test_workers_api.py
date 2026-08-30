"""Unit tests for backend/api/v1/workers.py helper functions."""

from unittest.mock import MagicMock, patch

import pytest

# ── _novnc_port ────────────────────────────────────────────────────────────────


def test_novnc_port_first_chrome():
    """chrome (no suffix) maps to base_port + 0."""
    from backend.api.v1.workers import _novnc_port

    assert _novnc_port("http://chrome:9222", 6080) == 6080


def test_novnc_port_second_agent():
    """agent-2 maps to base_port + 1."""
    from backend.api.v1.workers import _novnc_port

    assert _novnc_port("http://agent-2:9222", 6080) == 6081


def test_novnc_port_third_agent():
    """agent-3 maps to base_port + 2."""
    from backend.api.v1.workers import _novnc_port

    assert _novnc_port("http://agent-3:9222", 6080) == 6082


def test_novnc_port_unknown_hostname():
    """Unknown hostname pattern falls back to N=1."""
    from backend.api.v1.workers import _novnc_port

    assert _novnc_port("http://unknown-host:9222", 6080) == 6080


# ── _container_status ─────────────────────────────────────────────────────────


def test_container_status_running():
    """Returns 'running' when Docker container is running."""
    from backend.api.v1.workers import _container_status

    mock_container = MagicMock()
    mock_container.status = "running"
    mock_client = MagicMock()
    mock_client.containers.list.return_value = []
    mock_client.containers.get.return_value = mock_container

    with patch("docker.from_env", return_value=mock_client):
        status = _container_status("chrome")

    assert status == "running"


def test_container_status_docker_unavailable():
    """Returns 'unknown' when Docker is not available."""
    from backend.api.v1.workers import _container_status

    with patch("docker.from_env", side_effect=Exception("Docker not running")):
        status = _container_status("chrome")

    assert status == "unknown"


def test_container_status_import_error():
    """Returns 'unknown' when docker module not installed."""
    from backend.api.v1.workers import _container_status

    with patch.dict("sys.modules", {"docker": None}):
        status = _container_status("chrome")

    assert status == "unknown"


def test_container_status_looks_up_compose_service_label(monkeypatch):
    """Compose-generated names are resolved through service/project labels."""
    from backend.api.v1.workers import _container_status

    container = MagicMock(status="running", attrs={"State": {"Health": {"Status": "healthy"}}})
    mock_client = MagicMock()
    mock_client.containers.get.side_effect = Exception("generated name")
    mock_client.containers.list.return_value = [container]
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "opencli-admin")

    with patch("docker.from_env", return_value=mock_client):
        status = _container_status("agent-1")

    assert status == "running"
    mock_client.containers.get.assert_not_called()
    mock_client.containers.list.assert_called_once_with(
        all=True,
        filters={
            "label": [
                "com.docker.compose.service=agent-1",
                "com.docker.compose.project=opencli-admin",
            ]
        },
    )


def test_container_status_unhealthy_fails_closed():
    """A running container with an unhealthy healthcheck is not available."""
    from backend.api.v1.workers import _container_status

    container = MagicMock(status="running", attrs={"State": {"Health": {"Status": "unhealthy"}}})
    mock_client = MagicMock()
    mock_client.containers.list.return_value = []
    mock_client.containers.get.return_value = container

    with patch("docker.from_env", return_value=mock_client):
        status = _container_status("agent-1")

    assert status == "unhealthy"


# ── chrome_pool_status endpoint ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chrome_pool_status(client):
    """chrome-pool endpoint returns pool status dict."""
    from backend.browser_pool import init_pool

    # Initialize with a real pool so the endpoint works
    init_pool(["http://chrome:9222"], use_redis=False)

    with patch("backend.api.v1.workers._container_status", return_value="running"):
        response = await client.get("/api/v1/workers/chrome-pool")

    assert response.status_code == 200
    data = response.json()["data"]
    assert "endpoints" in data
    assert "total" in data
    assert "available" in data


@pytest.mark.asyncio
async def test_chrome_pool_status_uses_effective_availability_for_aggregate(client):
    """Known unhealthy slots are excluded from endpoint and aggregate counts."""
    from backend.browser_pool import init_pool

    init_pool(["http://agent-1:9222", "http://agent-2:9222"], use_redis=False)

    with patch(
        "backend.api.v1.workers._container_status",
        side_effect=["unhealthy", "running"],
    ):
        response = await client.get("/api/v1/workers/chrome-pool")

    assert response.status_code == 200
    data = response.json()["data"]
    assert [endpoint["available"] for endpoint in data["endpoints"]] == [False, True]
    assert data["available"] == 1


@pytest.mark.asyncio
async def test_chrome_pool_status_runtime_not_ready_is_unavailable(client):
    """Slots without a ready runtime must not be reported as available."""
    from backend.browser_pool import get_pool, init_pool

    init_pool(["http://agent-1:9222"], use_redis=False)
    get_pool().set_runtime_status("http://agent-1:9222", "DEGRADED")

    with patch("backend.api.v1.workers._container_status", return_value="unknown"):
        response = await client.get("/api/v1/workers/chrome-pool")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["endpoints"][0]["available"] is False
    assert data["available"] == 0


@pytest.mark.asyncio
async def test_chrome_pool_status_missing_compose_agent_fails_closed(client, monkeypatch):
    """A missing API-owned agent container is unavailable, not an unknown-ready slot."""
    from backend.browser_pool import init_pool

    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "opencli-admin")
    init_pool(["http://agent-1:9222"], use_redis=False)

    with patch("backend.api.v1.workers._container_status", return_value="unknown"):
        response = await client.get("/api/v1/workers/chrome-pool")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["endpoints"][0]["available"] is False
    assert data["available"] == 0


@pytest.mark.asyncio
async def test_chrome_pool_status_unknown_remote_fails_closed_without_positive_evidence(
    client, monkeypatch
):
    """Unverified non-Compose remote endpoints fail closed when Docker is unknown."""
    from backend.browser_pool import init_pool

    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
    init_pool(["http://remote-agent:9222"], use_redis=False)

    with patch("backend.api.v1.workers._container_status", return_value="unknown"):
        response = await client.get("/api/v1/workers/chrome-pool")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["endpoints"][0]["available"] is False
    assert data["available"] == 0


@pytest.mark.asyncio
async def test_chrome_pool_status_verified_remote_keeps_pool_semantics(client, monkeypatch):
    """A READY non-Compose remote endpoint remains available when Docker is unknown."""
    from backend.browser_pool import get_pool, init_pool

    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
    init_pool(["http://remote-agent:9222"], use_redis=False)
    get_pool().set_runtime_status("http://remote-agent:9222", "READY")

    with patch("backend.api.v1.workers._container_status", return_value="unknown"):
        response = await client.get("/api/v1/workers/chrome-pool")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["endpoints"][0]["available"] is True
    assert data["available"] == 1


@pytest.mark.asyncio
async def test_update_endpoint_mode_invalid_encoding(client):
    """PATCH with bad base64 encoding returns 400."""
    response = await client.patch(
        "/api/v1/workers/chrome-pool/!!!invalid!!!/mode",
        json={"mode": "cdp"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_endpoint_mode_not_in_pool(client):
    """PATCH with valid base64 but unknown endpoint returns 404."""
    import base64

    from backend.browser_pool import init_pool

    init_pool(["http://chrome:9222"], use_redis=False)

    unknown_ep = base64.urlsafe_b64encode(b"http://unknown:9222").decode()
    response = await client.patch(
        f"/api/v1/workers/chrome-pool/{unknown_ep}/mode",
        json={"mode": "cdp"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_endpoint_mode_success(client, db_session):
    """PATCH updates mode for a known endpoint."""
    import base64

    from backend.browser_pool import init_pool

    init_pool(["http://chrome:9222"], use_redis=False)

    encoded_ep = base64.urlsafe_b64encode(b"http://chrome:9222").decode()
    response = await client.patch(
        f"/api/v1/workers/chrome-pool/{encoded_ep}/mode",
        json={"mode": "cdp"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "cdp"
    assert data["endpoint"] == "http://chrome:9222"


@pytest.mark.asyncio
async def test_registered_anonymous_profile_is_visible_in_pool_inventory(client):
    """Agent registration is the authoritative public profile-routing seam."""
    from backend.browser_pool import init_pool

    init_pool([], use_redis=False)
    registered = await client.post(
        "/api/v1/nodes/register",
        json={
            "agent_url": "http://clean-agent:19823",
            "mode": "cdp",
            "node_type": "docker",
            "agent_protocol": "http",
            "profile_kind": "anonymous",
        },
    )
    assert registered.status_code == 200

    with patch("backend.api.v1.workers._container_status", return_value="running"):
        inventory = await client.get("/api/v1/workers/chrome-pool")

    assert inventory.status_code == 200
    assert inventory.json()["data"]["endpoints"] == [
        {
            "url": "http://clean-agent:19823",
            "available": True,
            "novnc_port": 6080,
            "container_status": "running",
            "mode": "cdp",
            "agent_url": "http://clean-agent:19823",
            "agent_protocol": "http",
            "profile_kind": "anonymous",
            "profile_name": "http://clean-agent:19823",
            "runtime_status": "LEGACY",
            "runtime_bundle_id": None,
            "runtime_bundle_name": None,
            "runtime_bundle_version": None,
            "resource_class": "standard",
            "startup_pages": [],
            "network_policy": {},
            "loaded_bundle_name": None,
            "loaded_bundle_version": None,
            "runtime_diagnostics": [],
        }
    ]
    # Module-level pool is shared across tests; restore its conservative bridge
    # default so this API contract test does not leak a live CDP probe target.
    init_pool(["http://localhost:9222"], use_redis=False)
