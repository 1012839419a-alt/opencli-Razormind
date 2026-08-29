"""Scoped, authenticated Studio endpoints for ResearchGraph V2 review."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.studio import StudioProject, StudioWorkflow, StudioWorkflowVersion
from backend.models.workflow_run import WorkflowRun
from backend.schemas.common import ApiResponse
from backend.schemas.research_graph_v2 import (
    ResearchGraphV2MutationRequest,
    ResearchGraphV2PinnedReference,
    ResearchGraphV2Read,
)
from backend.security.identity import RequestIdentity, get_request_identity
from backend.security.workspace_rbac import (
    WorkspacePermission,
    get_workspace_access,
    require_permission,
)
from backend.workflow.research_graph_v2 import (
    ResearchGraphV2ConflictError,
    ResearchGraphV2Scope,
    actor_evidence,
    append_research_graph_v2_mutation,
    read_research_graph_v2,
)

router = APIRouter(tags=["research-graph-v2"])


async def _scope(
    db: AsyncSession,
    *,
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
) -> ResearchGraphV2Scope:
    project = await db.get(StudioProject, project_id)
    if project is None or project.workspace_id != workspace_id or project.archived:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    workflow = await db.get(StudioWorkflow, workflow_id)
    if workflow is None or workflow.project_id != project_id or workflow.archived:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow not found")
    run = await db.get(WorkflowRun, run_id)
    if run is None or run.workflow_id != workflow_id or run.studio_workflow_version_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow run not found")
    version = await db.get(StudioWorkflowVersion, run.studio_workflow_version_id)
    if version is None or version.workflow_id != workflow_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow run not found")
    return ResearchGraphV2Scope(
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        studio_workflow_version_id=version.id,
        run_id=run.id,
    )


def _required_permission(action: str) -> WorkspacePermission:
    if action in {"verify", "reject", "retract", "pin", "supersede"}:
        return WorkspacePermission.APPROVE_ACTIONS
    return WorkspacePermission.WORK_INBOX


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/research-graph-v2",
    response_model=ApiResponse[ResearchGraphV2Read],
)
async def get_research_graph_v2(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    cursor: str | None = None,
    limit: int = 50,
    expected_pin_sequence: int | None = None,
    expected_pin_revision: str | None = None,
    expected_pin_manifest_set_hash: str | None = None,
    db: AsyncSession = Depends(get_db),
    identity: RequestIdentity = Depends(get_request_identity),
) -> ApiResponse[ResearchGraphV2Read]:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    scope = await _scope(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    expected_values = (
        expected_pin_sequence,
        expected_pin_revision,
        expected_pin_manifest_set_hash,
    )
    reference = (
        ResearchGraphV2PinnedReference(
            sequence=expected_pin_sequence,
            research_revision_id=expected_pin_revision,
            manifest_set_hash=expected_pin_manifest_set_hash,
        )
        if all(value is not None for value in expected_values)
        else None
    )
    return ApiResponse.ok(
        await read_research_graph_v2(
            db,
            scope=scope,
            cursor=cursor,
            limit=limit,
            pinned_reference=reference,
            require_pinned_reference=any(value is not None for value in expected_values),
        )
    )


@router.post(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/research-graph-v2/mutations",
    response_model=ApiResponse[ResearchGraphV2Read],
    status_code=status.HTTP_201_CREATED,
)
async def mutate_research_graph_v2(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    body: ResearchGraphV2MutationRequest,
    db: AsyncSession = Depends(get_db),
    identity: RequestIdentity = Depends(get_request_identity),
) -> ApiResponse[ResearchGraphV2Read]:
    access = await get_workspace_access(db, workspace_id, identity)
    permission = _required_permission(body.action)
    require_permission(access, permission)
    scope = await _scope(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    try:
        result = await append_research_graph_v2_mutation(
            db,
            scope=scope,
            actor=actor_evidence(
                actor_id=access.user_id,
                principal=identity.subject,
                capability=permission.value,
            ),
            request=body,
        )
        await db.commit()
    except ResearchGraphV2ConflictError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ApiResponse.ok(result)
