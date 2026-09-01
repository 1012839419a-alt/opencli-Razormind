from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.v1 import browser_spaces
from backend.database import get_db
from backend.security.identity import RequestIdentity, get_request_identity
from backend.security.workspace_rbac import WorkspaceAccess


class FakeServiceError(Exception):
    def __init__(self, code: str, status_code: int):
        self.code = code
        self.status_code = status_code


class FakeService:
    BrowserSpaceServiceError = FakeServiceError

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.space = SimpleNamespace(
            id="space-1",
            workspace_id="workspace-1",
            browser_instance_id="browser-1",
            binding_id=None,
            owner_type="operator",
            owner_id="user-1",
            status="idle",
            granted_capabilities=["snapshot"],
            revision=0,
            last_error_code=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.task = SimpleNamespace(id="task-1")

    async def create_space(self, _db, **kwargs):
        self.calls.append(("create_space", kwargs))
        return self.space

    async def get_space(self, _db, **kwargs):
        self.calls.append(("get_space", kwargs))
        await kwargs["authorizer"](self.space)
        return self.space

    async def list_spaces(self, _db, **kwargs):
        self.calls.append(("list_spaces", kwargs))
        await kwargs["authorizer"](self.space)
        return [self.space]

    async def submit_task(self, _db, **kwargs):
        self.calls.append(("submit_task", kwargs))
        await kwargs["authorizer"](self.space)
        return self.task

    async def cancel_space_task(self, _db, **kwargs):
        self.calls.append(("cancel_space_task", kwargs))
        await kwargs["authorizer"](self.space)
        return self.task

    async def close_space(self, _db, **kwargs):
        self.calls.append(("close_space", kwargs))
        await kwargs["authorizer"](self.space)
        return self.space

    async def list_events(self, _db, **kwargs):
        self.calls.append(("list_events", kwargs))
        await kwargs["authorizer"](self.space)
        return [
            SimpleNamespace(
                sequence=1,
                kind="queued",
                payload={"capability": "snapshot"},
                created_at=datetime.now(UTC),
            )
        ]

    def task_response(self, _task):
        return {
            "space_id": "space-1",
            "task_id": "task-1",
            "operation_id": "operation-1",
            "status": "queued",
            "result": None,
            "error": None,
        }


@pytest_asyncio.fixture
async def client(monkeypatch):
    app = FastAPI()
    app.include_router(browser_spaces.router, prefix="/api/v1")
    service = FakeService()
    monkeypatch.setattr(browser_spaces, "browser_space_service", service)

    async def identity():
        return RequestIdentity(subject="user-subject")

    async def db():
        yield object()

    async def access(_db, _workspace_id, _identity):
        return WorkspaceAccess(user_id="user-1", role="operator")

    app.dependency_overrides[get_request_identity] = identity
    app.dependency_overrides[get_db] = db
    monkeypatch.setattr(browser_spaces, "get_workspace_access", access)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as result:
        yield result, service


@pytest.mark.asyncio
async def test_create_space_uses_workspace_identity_and_hides_runtime_fields(client):
    http, service = client
    response = await http.post(
        "/api/v1/workspaces/workspace-1/browser-spaces",
        json={
            "browser_instance_id": "browser-1",
            "owner_type": "operator",
            "owner_id": "user-1",
            "granted_capabilities": ["snapshot"],
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["space_id"] == "space-1"
    assert "endpoint" not in response.json()["data"]
    assert service.calls[0][0] == "create_space"


@pytest.mark.asyncio
async def test_create_space_rejects_operator_owner_impersonation(client):
    http, service = client
    response = await http.post(
        "/api/v1/workspaces/workspace-1/browser-spaces",
        json={
            "browser_instance_id": "browser-1",
            "owner_type": "operator",
            "owner_id": "other-user",
            "granted_capabilities": ["snapshot"],
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "owner_not_authorized"
    assert service.calls == []


@pytest.mark.asyncio
async def test_submit_returns_accepted_and_passes_validated_args(client):
    http, service = client
    response = await http.post(
        "/api/v1/workspaces/workspace-1/browser-spaces/space-1/tasks",
        json={"request_id": "request-1", "capability": "snapshot", "args": {"selector": "main"}},
    )

    assert response.status_code == 202
    assert response.json()["data"]["operation_id"] == "operation-1"
    assert service.calls[0][1]["args"] == {"selector": "main"}


@pytest.mark.asyncio
async def test_service_errors_use_typed_status_and_code(client):
    http, service = client

    async def conflict(_db, **_kwargs):
        raise FakeServiceError("browser_instance_in_use", 409)

    service.create_space = conflict
    response = await http.post(
        "/api/v1/workspaces/workspace-1/browser-spaces",
        json={
            "browser_instance_id": "browser-1",
            "owner_type": "operator",
            "owner_id": "user-1",
            "granted_capabilities": ["snapshot"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "browser_instance_in_use"}


@pytest.mark.asyncio
async def test_event_replay_is_bounded_and_orders_parameters(client):
    http, service = client
    response = await http.get(
        "/api/v1/workspaces/workspace-1/browser-spaces/space-1/events?after_sequence=7&limit=100"
    )

    assert response.status_code == 200
    assert response.json()["data"][0]["sequence"] == 1
    assert service.calls[0][1]["after_sequence"] == 7
    assert service.calls[0][1]["limit"] == 100


@pytest.mark.asyncio
async def test_event_replay_rejects_limit_above_contract_bound(client):
    http, _service = client
    response = await http.get(
        "/api/v1/workspaces/workspace-1/browser-spaces/space-1/events?limit=101"
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unavailable_domain_service_is_a_typed_503(monkeypatch):
    app = FastAPI()
    app.include_router(browser_spaces.router, prefix="/api/v1")
    monkeypatch.setattr(browser_spaces, "browser_space_service", None)

    async def identity():
        return RequestIdentity(subject="user-subject")

    async def db():
        yield object()

    async def access(_db, _workspace_id, _identity):
        return WorkspaceAccess(user_id="user-1", role="operator")

    app.dependency_overrides[get_request_identity] = identity
    app.dependency_overrides[get_db] = db
    monkeypatch.setattr(browser_spaces, "get_workspace_access", access)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/api/v1/workspaces/workspace-1/browser-spaces")

    assert response.status_code == 503
    assert response.json()["detail"] == {"code": "browser_space_service_unavailable"}
