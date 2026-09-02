from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.security.identity import RequestIdentity


def _request(*, authorization: str = "", fleet_token: str = "") -> SimpleNamespace:
    headers = {}
    if authorization:
        headers["authorization"] = authorization
    if fleet_token:
        headers["x-api-token"] = fleet_token
    return SimpleNamespace(
        headers=headers,
        app=SimpleNamespace(state=SimpleNamespace(api_instance_id="accepting-process")),
    )


@pytest.mark.asyncio
async def test_restart_response_identifies_the_accepting_api_process(monkeypatch):
    from backend.api.v1 import browsers

    class FakeContainer:
        def restart(self) -> None:
            raise AssertionError("restart must remain delayed until after the response")

    container = FakeContainer()
    client = SimpleNamespace(containers=SimpleNamespace(get=lambda container_id: container))
    scheduled: list[tuple[float, object]] = []
    loop = SimpleNamespace(call_later=lambda delay, callback: scheduled.append((delay, callback)))
    request = _request()

    monkeypatch.setattr(browsers, "docker_client", lambda: client)
    monkeypatch.setattr(browsers.asyncio, "get_event_loop", lambda: loop)
    monkeypatch.setattr(browsers.socket, "gethostname", lambda: "api-container")

    response = await browsers.restart_api(
        request,
        RequestIdentity(subject="bootstrap-admin", is_platform_admin=True),
    )

    assert response.data == {
        "restarting": True,
        "container": "api-container",
        "instance_id": "accepting-process",
    }
    assert scheduled == [(1.0, container.restart)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity",
    [
        RequestIdentity(subject="fleet-agent", auth_method="fleet"),
        RequestIdentity(subject="oidc-user", claims={"roles": ["viewer"]}),
        RequestIdentity(subject="string-role", claims={"roles": "platform-admin"}),
        RequestIdentity(
            subject="substring-role",
            claims={"roles": ["tenant-platform-admin"]},
        ),
        RequestIdentity(
            subject="mapping-role",
            claims={"roles": {"platform-admin": True}},
        ),
    ],
)
async def test_restart_rejects_non_admin_identities_before_docker_access(monkeypatch, identity):
    from backend.api.v1 import browsers

    def unexpected_docker_access():
        raise AssertionError("unauthorized requests must not access Docker")

    monkeypatch.setattr(browsers, "docker_client", unexpected_docker_access)

    with pytest.raises(HTTPException) as exc_info:
        await browsers.restart_api(_request(), identity)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Platform administrator access required"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity",
    [
        RequestIdentity(
            subject="local-admin",
            auth_method="local",
            is_platform_admin=True,
        ),
        RequestIdentity(
            subject="bootstrap-admin",
            auth_method="bootstrap",
            is_platform_admin=True,
        ),
        RequestIdentity(
            subject="oidc-admin",
            claims={"roles": ["viewer", "platform-admin"]},
        ),
    ],
)
async def test_restart_allows_supported_admin_identities(monkeypatch, identity):
    from backend.api.v1 import browsers

    container = SimpleNamespace(restart=lambda: None)
    client = SimpleNamespace(containers=SimpleNamespace(get=lambda container_id: container))
    scheduled: list[tuple[float, object]] = []
    loop = SimpleNamespace(call_later=lambda delay, callback: scheduled.append((delay, callback)))

    monkeypatch.setattr(browsers, "docker_client", lambda: client)
    monkeypatch.setattr(browsers.asyncio, "get_event_loop", lambda: loop)
    monkeypatch.setattr(browsers.socket, "gethostname", lambda: "api-container")

    response = await browsers.restart_api(_request(), identity)

    assert response.data["restarting"] is True
    assert scheduled == [(1.0, container.restart)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authorization", "fleet_token"),
    [
        ("", "fleet-token"),
        ("Bearer fleet-token", ""),
    ],
)
async def test_fleet_transport_token_alone_is_forbidden(monkeypatch, authorization, fleet_token):
    from backend.api.v1 import browsers

    async def unexpected_identity_resolution(request):
        raise AssertionError("fleet transport token must not be resolved as an OIDC identity")

    monkeypatch.setattr(
        browsers,
        "get_settings",
        lambda: SimpleNamespace(api_auth_token="fleet-token"),
    )
    monkeypatch.setattr(browsers, "get_request_identity", unexpected_identity_resolution)

    with pytest.raises(HTTPException) as exc_info:
        await browsers._get_restart_request_identity(
            _request(authorization=authorization, fleet_token=fleet_token)
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Platform administrator access required"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {"X-API-Token": "fleet-token"},
        {"Authorization": "Bearer fleet-token"},
    ],
)
async def test_restart_route_returns_403_for_fleet_token_without_operator_identity(
    client, monkeypatch, headers
):
    from backend.api.v1 import browsers
    from backend.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "api_auth_token", "fleet-token")
    monkeypatch.setattr(
        browsers,
        "docker_client",
        lambda: (_ for _ in ()).throw(AssertionError("fleet-only requests must not access Docker")),
    )

    response = await client.post(
        "/api/v1/browsers/restart-api",
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Platform administrator access required"}
