"""Scoped Admin APIs for durable III OpenCLI collection commands."""

from __future__ import annotations

import secrets
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_db
from backend.models.iii_collection import IIICollectionAttemptV1
from backend.models.studio import StudioProject, StudioWorkflow, StudioWorkflowVersion
from backend.models.workflow_run import WorkflowRun
from backend.schemas.common import ApiResponse
from backend.schemas.iii_collection import (
    CollectorFinalExpectedKeyReportReadV1,
    CollectorFinalExpectedKeyReportV1,
    EvidenceBatchMaterializationReadV1,
    IIICollectionLifecycleReadV1,
    IIICollectionLifecycleV1,
    IIICollectionSubmitReadV1,
    IIICollectionSubmitV1,
    ODPIngressOutcomeReceiptReadV1,
    ODPIngressOutcomeReceiptV1,
    StudioEvidenceBatchMaterializationListV1,
    VerticalStatusV1,
)
from backend.workflow.evidence_batch_materializer import (
    get_materialization,
    get_materialization_by_batch,
    list_materializations,
    materialize_evidence_batch,
)
from backend.workflow.iii_collection_dispatch import dispatch_collection_attempt
from backend.workflow.iii_collection_store import (
    CollectionScope,
    IIICollectionConflictError,
    IIICollectionNotFoundError,
    cancel_collection,
    collection_status,
    get_scoped_command,
    ingest_expected_key_report,
    ingest_ingress_receipt,
    ingest_lifecycle,
    submission_read,
    submit_collection,
)

router = APIRouter(tags=["iii-collections"])


def _contains_node(graph: dict, node_id: str) -> bool:
    def walk(nodes: object) -> Iterator[dict]:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            yield node
            internals = node.get("internals")
            if isinstance(internals, dict):
                yield from walk(internals.get("nodes"))

    return any(str(node.get("id") or "") == node_id for node in walk(graph.get("nodes")))


async def _scoped_run(
    db: AsyncSession,
    *,
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
) -> tuple[CollectionScope, WorkflowRun, StudioWorkflowVersion]:
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
    return (
        CollectionScope(
            workspace_id=workspace_id,
            project_id=project_id,
            workflow_id=workflow_id,
            studio_workflow_version_id=version.id,
            run_id=run.id,
        ),
        run,
        version,
    )


@router.post(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/iii-collections",
    response_model=ApiResponse[IIICollectionSubmitReadV1],
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_iii_collection(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    body: IIICollectionSubmitV1,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[IIICollectionSubmitReadV1]:
    """Commit immutable Admin intent before dispatching it through III."""

    scope, run, version = await _scoped_run(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    if not _contains_node(version.graph, body.node_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Workflow node not found")
    try:
        submission = await submit_collection(
            db,
            scope=scope,
            run=run,
            node_id=body.node_id,
            idempotency_key=body.idempotency_key,
            collection=body.collection,
        )
    except IIICollectionConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await dispatch_collection_attempt(db, command=submission.command)
    return ApiResponse.ok(submission_read(submission))


@router.post(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/iii-collections/{command_id}/resume",
    response_model=ApiResponse[IIICollectionSubmitReadV1],
)
async def resume_iii_collection(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    command_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[IIICollectionSubmitReadV1]:
    """Re-deliver the already committed, unchanged attempt when it is eligible."""

    scope, _, _ = await _scoped_run(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    try:
        command = await get_scoped_command(db, scope=scope, command_id=command_id)
    except IIICollectionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    outbound = await dispatch_collection_attempt(db, command=command)
    attempt = (
        await db.execute(
            select(IIICollectionAttemptV1).where(IIICollectionAttemptV1.command_id == command.id)
        )
    ).scalar_one()
    return ApiResponse.ok(
        IIICollectionSubmitReadV1(
            command_id=command.id,
            attempt_id=attempt.id,
            attempt_number=attempt.attempt_number,
            task_id=attempt.task_id,
            trace_id=attempt.trace_id,
            payload_sha256=command.payload_sha256,
            created=False,
            dispatch_state=outbound.state,
        )
    )


@router.post(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/iii-collections/{command_id}/cancel",
    response_model=ApiResponse[VerticalStatusV1],
)
async def cancel_iii_collection(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    command_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[VerticalStatusV1]:
    scope, _, _ = await _scoped_run(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    try:
        command = await get_scoped_command(db, scope=scope, command_id=command_id)
    except IIICollectionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await cancel_collection(db, command=command)
    return ApiResponse.ok(await collection_status(db, command=command))


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/iii-collections/{command_id}",
    response_model=ApiResponse[VerticalStatusV1],
)
async def get_iii_collection_status(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    command_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[VerticalStatusV1]:
    scope, _, _ = await _scoped_run(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    try:
        command = await get_scoped_command(db, scope=scope, command_id=command_id)
    except IIICollectionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ApiResponse.ok(await collection_status(db, command=command))


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/iii-collections/{command_id}/materialization",
    response_model=ApiResponse[EvidenceBatchMaterializationReadV1],
)
async def get_iii_collection_materialization(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    command_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[EvidenceBatchMaterializationReadV1]:
    scope, _, _ = await _scoped_run(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    materialization = await get_materialization(db, scope=scope, command_id=command_id)
    if materialization is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence batch materialization not found")
    return ApiResponse.ok(materialization)


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/evidence-batches/v1",
    response_model=ApiResponse[StudioEvidenceBatchMaterializationListV1],
)
async def list_studio_evidence_batch_materializations(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    cursor: str | None = Query(default=None, min_length=1, max_length=36),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[StudioEvidenceBatchMaterializationListV1]:
    """Page latest redacted materialization summaries for one Studio run."""
    scope, _, _ = await _scoped_run(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    evidence_batches, next_cursor = await list_materializations(
        db,
        scope=scope,
        cursor=cursor,
        limit=limit,
    )
    return ApiResponse.ok(
        StudioEvidenceBatchMaterializationListV1(
            run_id=run_id,
            evidence_batches=evidence_batches,
            next_cursor=next_cursor,
        )
    )


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/evidence-batches/v1/{batch_id}",
    response_model=ApiResponse[EvidenceBatchMaterializationReadV1],
)
async def get_studio_evidence_batch_materialization(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    batch_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[EvidenceBatchMaterializationReadV1]:
    """Return one bounded, redacted latest evidence-batch detail projection."""
    scope, _, _ = await _scoped_run(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    materialization = await get_materialization_by_batch(db, scope=scope, batch_id=batch_id)
    if materialization is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence batch materialization not found")
    return ApiResponse.ok(materialization)


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/evidence-batches/v1/{batch_id}/status",
    response_model=ApiResponse[EvidenceBatchMaterializationReadV1],
)
async def get_studio_evidence_batch_materialization_status(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    batch_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[EvidenceBatchMaterializationReadV1]:
    """Return safe status, counts, and recovery for one evidence batch."""
    return await get_studio_evidence_batch_materialization(
        workspace_id,
        project_id,
        workflow_id,
        run_id,
        batch_id,
        db,
    )


@router.post(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/iii-collections/{command_id}/materialize",
    response_model=ApiResponse[EvidenceBatchMaterializationReadV1],
)
async def materialize_iii_collection(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    command_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[EvidenceBatchMaterializationReadV1]:
    """Reconcile retained facts and append one scoped immutable revision."""
    scope, _, _ = await _scoped_run(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )
    try:
        materialization = await materialize_evidence_batch(
            db, scope=scope, command_id=command_id
        )
    except IIICollectionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ApiResponse.ok(materialization)


@router.post(
    "/workspaces/{workspace_id}/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/iii-collections/{command_id}/recover",
    response_model=ApiResponse[EvidenceBatchMaterializationReadV1],
)
async def recover_iii_collection_materialization(
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    run_id: str,
    command_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[EvidenceBatchMaterializationReadV1]:
    """Safely retry reconciliation; it cannot alter a prior manifest."""
    return await materialize_iii_collection(
        workspace_id,
        project_id,
        workflow_id,
        run_id,
        command_id,
        db,
    )


@router.post(
    "/iii-collections/lifecycle",
    response_model=ApiResponse[IIICollectionLifecycleReadV1],
)
async def ingest_iii_collection_lifecycle(
    body: IIICollectionLifecycleV1,
    x_iii_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[IIICollectionLifecycleReadV1]:
    """Accept only validated, replay-safe lifecycle summaries from the III bridge."""

    configured_token = get_settings().iii_lifecycle_token
    if not configured_token or not secrets.compare_digest(
        configured_token, x_iii_bridge_token or ""
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid III bridge token")
    try:
        result = await ingest_lifecycle(db, event=body)
    except IIICollectionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except IIICollectionConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ApiResponse.ok(result)


@router.post(
    "/iii-collections/expected-key-reports",
    response_model=ApiResponse[CollectorFinalExpectedKeyReportReadV1],
)
async def ingest_iii_collection_expected_key_report(
    body: CollectorFinalExpectedKeyReportV1,
    x_iii_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CollectorFinalExpectedKeyReportReadV1]:
    """Append the bounded collector completion boundary through the III callback."""

    configured_token = get_settings().iii_lifecycle_token
    if not configured_token or not secrets.compare_digest(
        configured_token, x_iii_bridge_token or ""
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid III bridge token")
    try:
        result = await ingest_expected_key_report(db, report=body)
    except IIICollectionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except IIICollectionConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ApiResponse.ok(result)


@router.post(
    "/iii-collections/ingress-receipts",
    response_model=ApiResponse[ODPIngressOutcomeReceiptReadV1],
)
async def ingest_iii_collection_ingress_receipt(
    body: ODPIngressOutcomeReceiptV1,
    x_iii_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ODPIngressOutcomeReceiptReadV1]:
    """Append only a bridge-authenticated, producer-signed ingress observation."""

    configured_token = get_settings().iii_lifecycle_token
    if not configured_token or not secrets.compare_digest(
        configured_token, x_iii_bridge_token or ""
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid III bridge token")
    try:
        result = await ingest_ingress_receipt(db, receipt=body)
    except IIICollectionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except IIICollectionConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ApiResponse.ok(result)
