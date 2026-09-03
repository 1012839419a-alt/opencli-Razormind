"""Workspace-scoped API for governed coding workbench conversations."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from functools import partial

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, queue_after_commit
from backend.models.workbench import WorkbenchThread
from backend.schemas.common import ApiResponse
from backend.schemas.workbench import (
    WorkbenchEventRead,
    WorkbenchProposalRead,
    WorkbenchRepositoryRead,
    WorkbenchRuntimeRead,
    WorkbenchThreadCreate,
    WorkbenchThreadRead,
    WorkbenchTurnCreate,
    WorkbenchTurnRead,
)
from backend.security.identity import RequestIdentity, get_request_identity
from backend.security.workspace_rbac import (
    WorkspacePermission,
    get_workspace_access,
    require_permission,
)
from backend.services.workbench_service import (
    WorkbenchError,
    cancel_scheduled_workbench_turn,
    cancel_turn,
    confirm_proposal,
    create_turn,
    event_read,
    get_thread,
    get_turn,
    list_repositories,
    list_runtimes,
    list_threads,
    list_turn_events,
    schedule_workbench_turn,
    thread_read,
    turn_read,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/workbench", tags=["workbench"])


@router.get("/repositories", response_model=ApiResponse[list[WorkbenchRepositoryRead]])
async def get_repositories(
    workspace_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    repositories = await list_repositories(db, workspace_id)
    return ApiResponse.ok(
        [
            WorkbenchRepositoryRead(id=item.id, name=item.name, default_ref=item.base_ref)
            for item in repositories
        ]
    )


@router.get("/runtimes", response_model=ApiResponse[list[WorkbenchRuntimeRead]])
async def get_runtimes(
    workspace_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    return ApiResponse.ok(await list_runtimes(db, workspace_id))


@router.get("/threads", response_model=ApiResponse[list[WorkbenchThreadRead]])
async def get_threads(
    workspace_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    threads = await list_threads(db, workspace_id)
    return ApiResponse.ok([thread_read(thread) for thread in threads])


@router.post(
    "/threads",
    response_model=ApiResponse[WorkbenchThreadRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_thread(
    workspace_id: str,
    body: WorkbenchThreadCreate,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.RUN_OPERATIONS_AGENTS)
    thread = WorkbenchThread(
        workspace_id=workspace_id,
        repository_id=body.repository_id,
        title=body.title,
        created_by_user_id=access.user_id,
    )
    db.add(thread)
    await db.flush()
    try:
        turn = await create_turn(
            db,
            thread=thread,
            body=WorkbenchTurnCreate(
                runtime_id=body.runtime_id,
                requirement=body.requirement,
                request_id=body.request_id,
            ),
            user_id=access.user_id,
        )
    except WorkbenchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    queue_after_commit(db, partial(schedule_workbench_turn, turn.id))
    return ApiResponse.ok(
        thread_read(await get_thread(db, workspace_id, thread.id))
    )


@router.get("/threads/{thread_id}", response_model=ApiResponse[WorkbenchThreadRead])
async def get_thread_snapshot(
    workspace_id: str,
    thread_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    try:
        return ApiResponse.ok(thread_read(await get_thread(db, workspace_id, thread_id)))
    except WorkbenchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post(
    "/threads/{thread_id}/turns",
    response_model=ApiResponse[WorkbenchTurnRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_thread_turn(
    workspace_id: str,
    thread_id: str,
    body: WorkbenchTurnCreate,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.RUN_OPERATIONS_AGENTS)
    try:
        thread = await get_thread(db, workspace_id, thread_id, lock=True)
        turn = await create_turn(db, thread=thread, body=body, user_id=access.user_id)
    except WorkbenchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    queue_after_commit(db, partial(schedule_workbench_turn, turn.id))
    return ApiResponse.ok(turn_read(turn))


@router.get(
    "/threads/{thread_id}/turns/{turn_id}/events",
    response_model=ApiResponse[list[WorkbenchEventRead]],
)
async def get_events(
    workspace_id: str,
    thread_id: str,
    turn_id: str,
    after_sequence: int = Query(default=0, ge=0, alias="afterSequence"),
    limit: int = Query(default=500, ge=1, le=500),
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    try:
        turn = await get_turn(db, workspace_id=workspace_id, thread_id=thread_id, turn_id=turn_id)
    except WorkbenchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return ApiResponse.ok(
        [
            event_read(event)
            for event in await list_turn_events(
                db, turn=turn, after_sequence=after_sequence, limit=limit
            )
        ]
    )


@router.get("/threads/{thread_id}/turns/{turn_id}/events/stream")
async def stream_events(
    workspace_id: str,
    thread_id: str,
    turn_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0, alias="afterSequence"),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    if last_event_id is not None:
        try:
            after_sequence = max(0, int(last_event_id))
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Last-Event-ID must be a sequence"
            ) from exc
    try:
        await get_turn(db, workspace_id=workspace_id, thread_id=thread_id, turn_id=turn_id)
    except WorkbenchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return StreamingResponse(
        _stream_persisted_events(
            session=db,
            request=request,
            workspace_id=workspace_id,
            thread_id=thread_id,
            turn_id=turn_id,
            after_sequence=after_sequence,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/threads/{thread_id}/turns/{turn_id}/cancel", response_model=ApiResponse[WorkbenchTurnRead]
)
async def cancel_thread_turn(
    workspace_id: str,
    thread_id: str,
    turn_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.RUN_OPERATIONS_AGENTS)
    try:
        turn = await get_turn(
            db, workspace_id=workspace_id, thread_id=thread_id, turn_id=turn_id, lock=True
        )
        await cancel_turn(db, turn=turn, user_id=access.user_id)
        queue_after_commit(db, partial(cancel_scheduled_workbench_turn, turn.id))
    except WorkbenchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return ApiResponse.ok(turn_read(turn))


@router.post(
    "/threads/{thread_id}/proposals/{proposal_id}/confirm",
    response_model=ApiResponse[WorkbenchProposalRead],
)
async def confirm_thread_proposal(
    workspace_id: str,
    thread_id: str,
    proposal_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.APPROVE_ACTIONS)
    try:
        proposal = await confirm_proposal(
            db,
            workspace_id=workspace_id,
            thread_id=thread_id,
            proposal_id=proposal_id,
            user_id=access.user_id,
        )
    except WorkbenchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return ApiResponse.ok(
        WorkbenchProposalRead(
            id=proposal.id,
            status=proposal.status,
            base_sha=proposal.base_sha,
            checkpoint_sha=proposal.checkpoint_sha,
            diff=proposal.diff,
            modified_files=proposal.modified_files,
            tests=proposal.tests,
            error_message=proposal.error_message,
            confirmed_at=proposal.confirmed_at,
        )
    )


async def _stream_persisted_events(
    *,
    request: Request,
    session: AsyncSession,
    workspace_id: str,
    thread_id: str,
    turn_id: str,
    after_sequence: int,
) -> AsyncIterator[str]:
    cursor = after_sequence
    while True:
        try:
            turn = await get_turn(
                session,
                workspace_id=workspace_id,
                thread_id=thread_id,
                turn_id=turn_id,
            )
        except WorkbenchError:
            return
        events = [
            event_read(event)
            for event in await list_turn_events(session, turn=turn, after_sequence=cursor)
        ]
        turn_status = turn.status
        await session.rollback()
        for event in events:
            cursor = event.sequence
            yield _sse("workbench_event", event.model_dump_json(), event.sequence)
        if turn_status in {"proposed", "applied", "failed", "cancelled"} and not events:
            yield _sse("turn_state", json.dumps({"turnId": turn_id, "status": turn_status}), None)
            return
        if await request.is_disconnected():
            return
        await asyncio.sleep(0.25)


def _sse(event: str, data: str, sequence: int | None) -> str:
    identifier = "" if sequence is None else f"id: {sequence}\n"
    return f"{identifier}event: {event}\ndata: {data}\n\n"
