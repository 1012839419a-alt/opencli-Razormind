"""Workspace-scoped HTTP boundary for Browser Space ownership and task leases.

The Browser Space model and service land with the sibling domain change.  Imports
are deliberately lazy so this API slice does not change existing browser routes
until that dependency is integrated.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal, Protocol, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.common import ApiResponse
from backend.security.identity import RequestIdentity, get_request_identity
from backend.security.workspace_rbac import (
    WorkspaceAccess,
    WorkspacePermission,
    get_workspace_access,
    require_permission,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/browser-spaces", tags=["browser-spaces"])


class BrowserSpaceCreateRequest(BaseModel):
    browser_instance_id: str = Field(min_length=1)
    binding_id: str | None = None
    owner_type: Literal["operator", "runtime_agent"]
    owner_id: str = Field(min_length=1, max_length=255)
    granted_capabilities: list[str] = Field(min_length=1, max_length=100)


class BrowserSpaceTaskRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    capability: str = Field(min_length=1, max_length=255)
    args: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=60, ge=1, le=300)


class BrowserSpaceRead(BaseModel):
    space_id: str
    workspace_id: str
    browser_instance_id: str
    binding_id: str | None
    owner_type: str
    owner_id: str
    status: str
    granted_capabilities: list[str]
    revision: int
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime


class BrowserSpaceTaskRead(BaseModel):
    space_id: str
    task_id: str
    operation_id: str
    status: str
    result: dict[str, Any] | None
    error: dict[str, str] | None


class BrowserSpaceEventRead(BaseModel):
    sequence: int
    kind: str
    payload: dict[str, Any]
    created_at: datetime


class _BrowserSpaceService(Protocol):
    class BrowserSpaceServiceError(Exception):
        code: str
        status_code: int

    async def create_space(self, db: AsyncSession, **kwargs: Any) -> Any: ...
    async def get_space(self, db: AsyncSession, **kwargs: Any) -> Any: ...
    async def list_spaces(self, db: AsyncSession, **kwargs: Any) -> list[Any]: ...
    async def submit_task(self, db: AsyncSession, **kwargs: Any) -> Any: ...
    async def cancel_space_task(self, db: AsyncSession, **kwargs: Any) -> Any: ...
    async def close_space(self, db: AsyncSession, **kwargs: Any) -> Any: ...
    async def list_events(self, db: AsyncSession, **kwargs: Any) -> list[Any]: ...
    def task_response(self, task: Any) -> dict[str, Any]: ...


# Test seams may replace this value. The production import remains lazy because
# the service is delivered by the sibling domain commit.
browser_space_service: _BrowserSpaceService | None = None


def _service() -> _BrowserSpaceService:
    global browser_space_service
    if browser_space_service is None:
        try:
            from backend.services import browser_space_service as resolved_service
        except ImportError as exc:  # pragma: no cover - protects pre-integration deployments
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"code": "browser_space_service_unavailable"},
            ) from exc
        browser_space_service = cast(_BrowserSpaceService, resolved_service)
    return browser_space_service


def _service_error(service: _BrowserSpaceService, code: str, status_code: int) -> Exception:
    return service.BrowserSpaceServiceError(code, status_code)


async def _authorize_space(space: Any, access: WorkspaceAccess) -> None:
    """Allow an operator's own Space or a permitted runtime-agent controller."""
    service = _service()
    if space.owner_type == "operator" and space.owner_id == access.user_id:
        return
    if (
        space.owner_type == "runtime_agent"
        and access.allows(WorkspacePermission.RUN_OPERATIONS_AGENTS)
    ):
        return
    raise _service_error(service, "owner_not_authorized", status.HTTP_403_FORBIDDEN)


def _map_service_error(exc: Exception) -> HTTPException:
    code = str(getattr(exc, "code", "browser_space_error"))[:64]
    status_code = int(getattr(exc, "status_code", status.HTTP_422_UNPROCESSABLE_CONTENT))
    return HTTPException(status_code, detail={"code": code})


async def _call(call: Callable[[], Awaitable[Any]]) -> Any:
    service = _service()
    try:
        return await call()
    except service.BrowserSpaceServiceError as exc:
        raise _map_service_error(exc) from exc


def _space_read(space: Any) -> BrowserSpaceRead:
    return BrowserSpaceRead(
        space_id=str(space.id),
        workspace_id=str(space.workspace_id),
        browser_instance_id=str(space.browser_instance_id),
        binding_id=str(space.binding_id) if space.binding_id is not None else None,
        owner_type=space.owner_type,
        owner_id=str(space.owner_id),
        status=space.status,
        granted_capabilities=list(space.granted_capabilities),
        revision=space.revision,
        last_error_code=space.last_error_code,
        created_at=space.created_at,
        updated_at=space.updated_at,
    )


def _task_read(task: Any) -> BrowserSpaceTaskRead:
    response = _service().task_response(task)
    error = response.get("error")
    return BrowserSpaceTaskRead(
        space_id=str(response["space_id"]),
        task_id=str(response["task_id"]),
        operation_id=str(response["operation_id"]),
        status=response["status"],
        result=response.get("result"),
        error=error if isinstance(error, dict) else None,
    )


def _event_read(event: Any) -> BrowserSpaceEventRead:
    return BrowserSpaceEventRead(
        sequence=event.sequence,
        kind=event.kind,
        payload=event.payload if isinstance(event.payload, dict) else {},
        created_at=event.created_at,
    )


async def _workspace_access(
    workspace_id: str, identity: RequestIdentity, db: AsyncSession
) -> WorkspaceAccess:
    return await get_workspace_access(db, workspace_id, identity)


@router.get("", response_model=ApiResponse[list[BrowserSpaceRead]])
async def list_browser_spaces(
    workspace_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[BrowserSpaceRead]]:
    access = await _workspace_access(workspace_id, identity, db)
    require_permission(access, WorkspacePermission.READ)
    spaces = await _call(
        lambda: _service().list_spaces(
            db,
            workspace_id=workspace_id,
            limit=limit,
            authorizer=lambda space: _authorize_space(space, access),
        )
    )
    return ApiResponse.ok([_space_read(space) for space in spaces])


@router.post("", response_model=ApiResponse[BrowserSpaceRead], status_code=status.HTTP_201_CREATED)
async def create_browser_space(
    workspace_id: str,
    body: BrowserSpaceCreateRequest,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[BrowserSpaceRead]:
    access = await _workspace_access(workspace_id, identity, db)
    require_permission(access, WorkspacePermission.RUN_OPERATIONS_AGENTS)
    if body.owner_type == "operator" and body.owner_id != access.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "owner_not_authorized"})
    space = await _call(
        lambda: _service().create_space(
            db,
            workspace_id=workspace_id,
            browser_instance_id=body.browser_instance_id,
            binding_id=body.binding_id,
            owner_type=body.owner_type,
            owner_id=body.owner_id,
            granted_capabilities=body.granted_capabilities,
        )
    )
    return ApiResponse.ok(_space_read(space))


@router.get("/{space_id}", response_model=ApiResponse[BrowserSpaceRead])
async def get_browser_space(
    workspace_id: str,
    space_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[BrowserSpaceRead]:
    access = await _workspace_access(workspace_id, identity, db)
    require_permission(access, WorkspacePermission.READ)
    space = await _call(
        lambda: _service().get_space(
            db,
            workspace_id=workspace_id,
            space_id=space_id,
            authorizer=lambda value: _authorize_space(value, access),
        )
    )
    return ApiResponse.ok(_space_read(space))


@router.post(
    "/{space_id}/tasks",
    response_model=ApiResponse[BrowserSpaceTaskRead],
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_browser_space_task(
    workspace_id: str,
    space_id: str,
    body: BrowserSpaceTaskRequest,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[BrowserSpaceTaskRead]:
    access = await _workspace_access(workspace_id, identity, db)
    require_permission(access, WorkspacePermission.RUN_OPERATIONS_AGENTS)
    task = await _call(
        lambda: _service().submit_task(
            db,
            workspace_id=workspace_id,
            space_id=space_id,
            request_id=body.request_id,
            capability=body.capability,
            args=body.args,
            authorizer=lambda value: _authorize_space(value, access),
        )
    )
    return ApiResponse.ok(_task_read(task))


@router.post("/{space_id}/cancel", response_model=ApiResponse[BrowserSpaceTaskRead | None])
async def cancel_browser_space_task(
    workspace_id: str,
    space_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[BrowserSpaceTaskRead | None]:
    access = await _workspace_access(workspace_id, identity, db)
    require_permission(access, WorkspacePermission.RUN_OPERATIONS_AGENTS)
    task = await _call(
        lambda: _service().cancel_space_task(
            db,
            workspace_id=workspace_id,
            space_id=space_id,
            authorizer=lambda value: _authorize_space(value, access),
        )
    )
    return ApiResponse.ok(_task_read(task) if task is not None else None)


@router.post("/{space_id}/close", response_model=ApiResponse[BrowserSpaceRead])
async def close_browser_space(
    workspace_id: str,
    space_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[BrowserSpaceRead]:
    access = await _workspace_access(workspace_id, identity, db)
    require_permission(access, WorkspacePermission.RUN_OPERATIONS_AGENTS)
    space = await _call(
        lambda: _service().close_space(
            db,
            workspace_id=workspace_id,
            space_id=space_id,
            authorizer=lambda value: _authorize_space(value, access),
        )
    )
    return ApiResponse.ok(_space_read(space))


@router.get("/{space_id}/events", response_model=ApiResponse[list[BrowserSpaceEventRead]])
async def list_browser_space_events(
    workspace_id: str,
    space_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[BrowserSpaceEventRead]]:
    access = await _workspace_access(workspace_id, identity, db)
    require_permission(access, WorkspacePermission.READ)
    events = await _call(
        lambda: _service().list_events(
            db,
            workspace_id=workspace_id,
            space_id=space_id,
            after_sequence=after_sequence,
            limit=limit,
            authorizer=lambda value: _authorize_space(value, access),
        )
    )
    return ApiResponse.ok([_event_read(event) for event in events])
