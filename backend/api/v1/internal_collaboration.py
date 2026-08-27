"""Authenticated Studio Draft collaboration boundary for the Yjs sidecar."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.v1.collaboration_schemas import (
    CollaborationRoomRead,
    CollaborationRoomRequest,
    CollaborationSnapshotRead,
    CollaborationSnapshotRequest,
)
from backend.api.v1.studio_helpers import canonicalize_studio_graph, get_workflow
from backend.database import get_db
from backend.models.studio import StudioWorkflowDraft
from backend.schemas import workflow as workflow_schemas
from backend.schemas.common import ApiResponse

router = APIRouter(prefix="/internal/collaboration", tags=["internal-collaboration"])

# Snapshot calls originate in the self-hosted collaboration sidecar. The API's
# fleet-token middleware authenticates that service before this router runs.
COLLABORATION_ACTOR_ID = "collaboration-service"
_ROOM_LABELS = ("workspace", "project", "workflow")


def collaboration_room(*, workspace_id: str, project_id: str, workflow_id: str) -> str:
    """Return the sole permitted room name for a Studio workflow."""

    return f"workspace:{workspace_id}:project:{project_id}:workflow:{workflow_id}"


def parse_collaboration_room(room: str) -> tuple[str, str, str]:
    """Parse a canonical Studio workflow room without accepting aliases."""

    parts = room.split(":")
    if (
        len(parts) != 6
        or tuple(parts[::2]) != _ROOM_LABELS
        or any(not part or part != part.strip() for part in parts[1::2])
    ):
        raise ValueError("Invalid collaboration room")
    workspace_id, project_id, workflow_id = parts[1::2]
    if collaboration_room(
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
    ) != room:
        raise ValueError("Invalid collaboration room")
    return workspace_id, project_id, workflow_id


async def _owned_workflow_from_room(
    db: AsyncSession, room: str
) -> tuple[str, str, str]:
    try:
        workspace_id, project_id, workflow_id = parse_collaboration_room(room)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await get_workflow(db, workspace_id, project_id, workflow_id)
    return workspace_id, project_id, workflow_id


def _map_values(content: Mapping[str, dict], kind: str) -> list[dict]:
    """Convert a Y.Map JSON object to graph entries while rejecting duplicate IDs."""

    entries = list(content.values())
    if any(entry.get("id") != map_key for map_key, entry in content.items()):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Collaboration {kind} map key does not match entry id",
        )
    ids = [entry.get("id") for entry in entries]
    if any(not isinstance(entry_id, str) for entry_id in ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Collaboration {kind} map has an entry without a string id",
        )
    if len(ids) != len(set(ids)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Collaboration {kind} map contains duplicate ids",
        )
    return entries


@router.post(
    "/authorize",
    response_model=ApiResponse[CollaborationRoomRead],
)
async def authorize_collaboration_room(
    body: CollaborationRoomRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """Authorize one websocket room through the workflow ownership hierarchy."""

    workspace_id, project_id, workflow_id = await _owned_workflow_from_room(db, body.room)
    return ApiResponse.ok(
        CollaborationRoomRead(
            room=collaboration_room(
                workspace_id=workspace_id,
                project_id=project_id,
                workflow_id=workflow_id,
            )
        )
    )


@router.post(
    "/snapshot",
    response_model=ApiResponse[CollaborationSnapshotRead],
)
async def snapshot_collaboration_draft(
    body: CollaborationSnapshotRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """Durably apply a Yjs graph snapshot without replacing Draft metadata."""

    _, _, workflow_id = await _owned_workflow_from_room(db, body.room)
    draft = await db.scalar(
        select(StudioWorkflowDraft)
        .where(StudioWorkflowDraft.workflow_id == workflow_id)
        .with_for_update()
    )
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow draft not found")

    graph = {
        **draft.graph,
        "nodes": _map_values(body.data.nodes.content, "nodes"),
        "edges": _map_values(body.data.edges.content, "edges"),
    }
    try:
        workflow_schemas.WorkflowProject.model_validate({**graph, "id": workflow_id})
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Invalid collaboration graph",
        ) from exc

    draft.graph = canonicalize_studio_graph(graph, workflow_id=workflow_id)
    draft.revision += 1
    draft.updated_by_user_id = COLLABORATION_ACTOR_ID
    await db.flush()
    return ApiResponse.ok(CollaborationSnapshotRead(revision=draft.revision))
