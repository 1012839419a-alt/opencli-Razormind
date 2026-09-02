"""Workflow asset and mutable Draft routes for Studio."""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.v1.studio_helpers import (
    LOCAL_USER_ID,
    canonicalize_studio_graph,
    get_project,
    get_workflow,
)
from backend.api.v1.studio_schemas import (
    DraftRead,
    DraftUpdate,
    ProjectRuntimeLogRead,
    ProjectRuntimeSummaryRead,
    ProjectRuntimeTraceRead,
    PublishedWorkflowRunStart,
    WorkflowCreate,
    WorkflowRead,
)
from backend.api.v1.workflows import (
    build_evidence_projection,
    dispatch_materialized_image_jobs,
    get_evidence_batch,
    list_evidence_batches,
    parse_projection_includes,
)
from backend.database import get_db
from backend.models.studio import (
    StudioProject,
    StudioWorkflow,
    StudioWorkflowDraft,
    StudioWorkflowVersion,
)
from backend.models.workflow_run import WorkflowRun
from backend.schemas import workflow as workflow_schemas
from backend.schemas.common import ApiResponse, PaginationMeta
from backend.workflow.opencli_hda_tracer import (
    get_workflow_run_checkpoint,
    get_workflow_run_projection,
    list_workflow_run_events,
    replay_downstream_from_persisted_gaojixing_source,
    start_workflow_run,
)

router = APIRouter()


def _runtime_log(
    row: WorkflowRun,
    *,
    workflow_names: dict[str, str],
    version_numbers: dict[str, int],
) -> ProjectRuntimeLogRead:
    projection = row.projection or {}
    request = row.request or {}
    duration_ms = max(0, int((row.updated_at - row.created_at).total_seconds() * 1000))
    return ProjectRuntimeLogRead(
        run_id=row.id,
        workflow_id=row.workflow_id,
        workflow_name=workflow_names.get(row.workflow_id, "未知工作流"),
        workflow_version=version_numbers.get(row.studio_workflow_version_id or ""),
        trace_id=row.trace_id,
        status=row.status,
        trigger=str((request.get("trigger") or {}).get("kind") or "manual"),
        response_mode=request.get("responseMode") or "async",
        event_count=int(projection.get("eventCount", 0)),
        node_count=len(projection.get("nodeStates", []) or []),
        error_count=len(projection.get("errors", []) or []),
        duration_ms=duration_ms,
        started_at=row.created_at,
        updated_at=row.updated_at,
    )


def _default_published_trigger_kind(
    project: workflow_schemas.WorkflowProject,
    trigger_node_id: str | None,
) -> workflow_schemas.WorkflowRunTriggerKind:
    """Choose the graph's real trigger when Studio Run omits one.

    The authoring UI historically posted ``manual`` unconditionally.  That
    silently makes schedule-only workflows fail before any node executes.  A
    direct Studio/CLI run is still an explicit run, but it must enter through
    the trigger entry that actually exists in the published graph.
    """
    nodes = project.nodes
    if trigger_node_id:
        selected = next((node for node in nodes if node.id == trigger_node_id), None)
        if selected is not None:
            if selected.kind == "webhook":
                return "webhook"
            if selected.kind == "schedule":
                params = selected.params
                builder = params.get("builder")
                if params.get("mode") == "manual" or (
                    isinstance(builder, dict) and builder.get("nodeType") == "manual-trigger"
                ):
                    return "manual"
                return "schedule"

    for node in nodes:
        if node.kind == "schedule" and (
            node.params.get("mode") == "manual"
            or (
                isinstance(node.params.get("builder"), dict)
                and node.params["builder"].get("nodeType") == "manual-trigger"
            )
        ):
            return "manual"
    if any(node.kind == "schedule" for node in nodes):
        return "schedule"
    if any(node.kind == "webhook" for node in nodes):
        return "webhook"
    return "manual"


async def _project_runtime_scope(
    db: AsyncSession,
    *,
    workspace_id: str,
    project_id: str,
) -> tuple[dict[str, str], dict[str, int]]:
    await get_project(db, workspace_id, project_id)
    workflows = list(
        (
            await db.execute(
                select(StudioWorkflow).where(
                    StudioWorkflow.project_id == project_id,
                    StudioWorkflow.archived.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    workflow_names = {workflow.id: workflow.name for workflow in workflows}
    if not workflow_names:
        return workflow_names, {}
    versions = list(
        (
            await db.execute(
                select(StudioWorkflowVersion).where(
                    StudioWorkflowVersion.workflow_id.in_(workflow_names)
                )
            )
        )
        .scalars()
        .all()
    )
    return workflow_names, {version.id: version.version for version in versions}



@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows",
    response_model=ApiResponse[list[WorkflowRead]],
)
async def list_workflows(
    workspace_id: str, project_id: str, db: AsyncSession = Depends(get_db)
) -> ApiResponse:
    await get_project(db, workspace_id, project_id)
    rows = (
        (
            await db.execute(
                select(StudioWorkflow)
                .where(
                    StudioWorkflow.project_id == project_id,
                    StudioWorkflow.archived.is_(False),
                )
                .order_by(StudioWorkflow.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return ApiResponse.ok([WorkflowRead.model_validate(row) for row in rows])


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/runtime-summary",
    response_model=ApiResponse[ProjectRuntimeSummaryRead],
)
async def get_project_runtime_summary(
    workspace_id: str,
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """Summarize persisted workflow runs for one Studio Project."""

    workflow_names, version_numbers = await _project_runtime_scope(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    if not workflow_names:
        return ApiResponse.ok(
            ProjectRuntimeSummaryRead(
                total_runs=0,
                successful_runs=0,
                failed_runs=0,
                blocked_runs=0,
                running_runs=0,
                total_events=0,
                recent_logs=[],
            )
        )

    # ponytail: scan compact projection rows here; add maintained counters only
    # when project run volume makes this operator-page query measurable.
    aggregate_rows = list(
        (
            await db.execute(
                select(WorkflowRun.status, WorkflowRun.projection).where(
                    WorkflowRun.workflow_id.in_(workflow_names)
                )
            )
        ).all()
    )
    recent_rows = list(
        (
            await db.execute(
                select(WorkflowRun)
                .where(WorkflowRun.workflow_id.in_(workflow_names))
                .order_by(WorkflowRun.created_at.desc())
                .limit(8)
            )
        )
        .scalars()
        .all()
    )
    successful = {"completed", "partial_success"}
    failed = {"failed"}
    blocked = {"blocked"}
    running = {"queued", "running", "waiting", "partial"}

    return ApiResponse.ok(
        ProjectRuntimeSummaryRead(
            total_runs=len(aggregate_rows),
            successful_runs=sum(1 for row in aggregate_rows if row.status in successful),
            failed_runs=sum(1 for row in aggregate_rows if row.status in failed),
            blocked_runs=sum(1 for row in aggregate_rows if row.status in blocked),
            running_runs=sum(1 for row in aggregate_rows if row.status in running),
            total_events=sum(
                int((row.projection or {}).get("eventCount", 0)) for row in aggregate_rows
            ),
            recent_logs=[
                _runtime_log(
                    row,
                    workflow_names=workflow_names,
                    version_numbers=version_numbers,
                )
                for row in recent_rows
            ],
        )
    )


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/runtime-logs",
    response_model=ApiResponse[list[ProjectRuntimeLogRead]],
)
async def list_project_runtime_logs(
    workspace_id: str,
    project_id: str,
    run_status: workflow_schemas.WorkflowRunStatus | None = Query(
        default=None,
        alias="status",
    ),
    search: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """List durable Workflow Runs owned by one Studio Project."""

    workflow_names, version_numbers = await _project_runtime_scope(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    if not workflow_names:
        return ApiResponse.ok(
            [],
            meta=PaginationMeta(total=0, page=page, limit=limit, pages=1),
        )

    filters = [WorkflowRun.workflow_id.in_(workflow_names)]
    if run_status:
        filters.append(WorkflowRun.status == run_status)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                WorkflowRun.id.ilike(pattern),
                WorkflowRun.trace_id.ilike(pattern),
                WorkflowRun.workflow_id.ilike(pattern),
            )
        )

    total = int(await db.scalar(select(func.count()).select_from(WorkflowRun).where(*filters)) or 0)
    rows = list(
        (
            await db.execute(
                select(WorkflowRun)
                .where(*filters)
                .order_by(WorkflowRun.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return ApiResponse.ok(
        [
            _runtime_log(
                row,
                workflow_names=workflow_names,
                version_numbers=version_numbers,
            )
            for row in rows
        ],
        meta=PaginationMeta(
            total=total,
            page=page,
            limit=limit,
            pages=max(1, -(-total // limit)),
        ),
    )


@router.post(
    ("/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs"),
    response_model=ApiResponse[workflow_schemas.WorkflowRunProjection],
    status_code=202,
)
async def start_published_workflow_run(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    body: PublishedWorkflowRunStart,
    idempotency_header: str | None = Header(default=None, alias="Idempotency-Key"),
    request_id_header: str | None = Header(default=None, alias="X-Request-ID"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """Run the immutable published graph without accepting graph replacement."""

    workflow = await get_workflow(db, workspace_id, project_id, workflow_id)
    if workflow.current_published_version is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Workflow must be published before API execution",
        )
    version = await db.scalar(
        select(StudioWorkflowVersion).where(
            StudioWorkflowVersion.workflow_id == workflow_id,
            StudioWorkflowVersion.version == workflow.current_published_version,
        )
    )
    if version is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Published workflow version is unavailable",
        )

    request_id = body.request_id or request_id_header or str(uuid.uuid4())
    idempotency_key = body.idempotency_key or idempotency_header
    run_id = None
    if idempotency_key:
        run_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    "opencli-admin:studio-run:"
                    f"{workspace_id}:{project_id}:{workflow_id}:{version.id}:{idempotency_key}"
                ),
            )
        )
        existing = await db.get(WorkflowRun, run_id)
        if existing is not None:
            if (
                existing.workflow_id != workflow_id
                or existing.studio_workflow_version_id != version.id
            ):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Idempotency key collides with another workflow run",
                )
            projection = await get_workflow_run_projection(run_id, session=db)
            if projection is not None:
                return ApiResponse.ok(projection)

    project = workflow_schemas.WorkflowProject.model_validate(version.graph)
    trigger_kind = body.trigger_kind or _default_published_trigger_kind(
        project, body.trigger_node_id
    )
    projection = await start_workflow_run(
        workflow_schemas.WorkflowRunStartRequest(
            project=project,
            runId=run_id,
            trigger=workflow_schemas.WorkflowRunTrigger(
                kind=trigger_kind,
                triggerNodeId=body.trigger_node_id,
                requestId=request_id,
                idempotencyKey=idempotency_key,
            ),
            input=workflow_schemas.WorkflowRunInput(
                payload=body.inputs,
                source="external",
                sourceId=body.user,
            ),
            responseMode=body.response_mode,
        ),
        session=db,
        studio_workflow_version_id=version.id,
    )
    await dispatch_materialized_image_jobs(db, projection.runId)
    return ApiResponse.ok(projection)


@router.post(
    (
        "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}"
        "/runs/{run_id}/downstream-replay"
    ),
    response_model=ApiResponse[workflow_schemas.WorkflowRunProjection],
    status_code=202,
)
async def replay_persisted_gaojixing_source_downstream(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """Replay normalization through sink from completed persisted Gaojixing evidence."""

    workflow = await get_workflow(db, workspace_id, project_id, workflow_id)
    if workflow.current_published_version is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Workflow must be published before downstream replay"
        )
    version = await db.scalar(
        select(StudioWorkflowVersion).where(
            StudioWorkflowVersion.workflow_id == workflow_id,
            StudioWorkflowVersion.version == workflow.current_published_version,
        )
    )
    if version is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Published workflow version is unavailable")
    await _get_project_workflow_run(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    try:
        projection = await replay_downstream_from_persisted_gaojixing_source(
            run_id,
            expected_workflow_id=workflow_id,
            expected_studio_workflow_version_id=version.id,
            session=db,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ApiResponse.ok(projection)


@router.get(
    (
        "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}"
        "/runs/{run_id}/trace"
    ),
    response_model=ApiResponse[ProjectRuntimeTraceRead],
)
async def get_project_runtime_trace(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    after_sequence: int | None = Query(default=None, ge=0, alias="afterSequence"),
    limit: int | None = Query(default=None, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """Return one project-owned run trace without opening generic run access."""

    row, workflow_version = await _get_project_workflow_run(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    projection = await get_workflow_run_projection(run_id, session=db)
    checkpoint = await get_workflow_run_checkpoint(run_id, session=db)
    events = await list_workflow_run_events(
        run_id,
        session=db,
        after_sequence=after_sequence,
        limit=limit,
    )
    if projection is None or checkpoint is None or events is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow run not found")
    request = row.request or {}
    input_payload = request.get("input") or {}
    return ApiResponse.ok(
        ProjectRuntimeTraceRead(
            workflow_version=workflow_version,
            inputs=input_payload.get("payload") or {},
            user=input_payload.get("sourceId"),
            response_mode=request.get("responseMode") or "async",
            trace=workflow_schemas.WorkflowRunTraceResponse(
                projection=projection,
                checkpoint=checkpoint,
                events=events,
                filters={"afterSequence": after_sequence, "limit": limit},
                nextAfterSequence=max(
                    (event.sequence for event in events),
                    default=after_sequence or 0,
                ),
            ),
        )
    )



@router.post(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows",
    response_model=ApiResponse[WorkflowRead],
    status_code=201,
)
async def create_workflow(
    workspace_id: str,
    project_id: str,
    body: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    project = await db.scalar(
        select(StudioProject)
        .where(
            StudioProject.id == project_id,
            StudioProject.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    row = StudioWorkflow(project_id=project_id, name=body.name, description=body.description)
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow name already exists") from exc
    graph = canonicalize_studio_graph(body.graph, workflow_id=row.id)
    db.add(
        StudioWorkflowDraft(
            workflow_id=row.id,
            graph=graph,
            updated_by_user_id=LOCAL_USER_ID,
        )
    )
    await db.flush()
    if project.primary_workflow_id is None:
        project.primary_workflow_id = row.id
        await db.flush()
    return ApiResponse.ok(WorkflowRead.model_validate(row))


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/draft",
    response_model=ApiResponse[DraftRead],
)
async def get_draft(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    await get_workflow(db, workspace_id, project_id, workflow_id)
    row = await db.scalar(
        select(StudioWorkflowDraft).where(StudioWorkflowDraft.workflow_id == workflow_id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow draft not found")
    draft = DraftRead.model_validate(row, from_attributes=True)
    return ApiResponse.ok(
        draft.model_copy(
            update={
                "graph": workflow_schemas.WorkflowProject.model_validate(
                    canonicalize_studio_graph(
                        draft.graph,
                        workflow_id=workflow_id,
                    )
                )
            }
        )
    )


@router.put(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/draft",
    response_model=ApiResponse[DraftRead],
)
async def update_draft(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    body: DraftUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    await get_workflow(db, workspace_id, project_id, workflow_id)
    row = await db.scalar(
        select(StudioWorkflowDraft)
        .where(StudioWorkflowDraft.workflow_id == workflow_id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow draft not found")
    if row.revision != body.revision:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow draft revision conflict")
    row.graph = canonicalize_studio_graph(body.graph, workflow_id=workflow_id)
    row.revision += 1
    row.updated_by_user_id = LOCAL_USER_ID
    await db.flush()
    return ApiResponse.ok(DraftRead.model_validate(row, from_attributes=True))
