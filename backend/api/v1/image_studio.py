"""Platform-owned ImageStudio API; never exposes InvokeAI credentials or URLs."""

import json
from collections.abc import AsyncIterator
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.v1.studio_helpers import LOCAL_USER_ID
from backend.config import get_settings
from backend.database import get_db
from backend.image_studio.invoke_client import (
    InvokeAIClient,
    InvokeAIClientError,
    InvokeAIConnection,
)
from backend.image_studio.worker_runtime import dispatch_block_reason
from backend.models.image_studio import ImageGenerationJobStatus
from backend.schemas.common import ApiResponse
from backend.schemas.image_studio import (
    CanvasDocumentCreate,
    CanvasDocumentRead,
    CanvasDocumentSave,
    CanvasSnapshotCreate,
    CanvasSnapshotRead,
    ImageGenerationJobCreate,
    ImageGenerationJobRead,
    ImageModelRead,
    MediaAssetRead,
)
from backend.services import image_studio_service as service

router = APIRouter(
    prefix="/workspaces/{workspace_id}/projects/{project_id}/image-studio",
    tags=["image-studio"],
)


def _translate_error(exc: service.ImageStudioError) -> HTTPException:
    if isinstance(exc, service.ImageStudioNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, (service.RevisionConflictError, service.ImageStudioConflictError)):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(
        exc,
        (
            service.SnapshotValidationError,
            service.MediaAssetValidationError,
            service.InvalidJobTransitionError,
        ),
    ):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "ImageStudio operation failed")


@router.post(
    "/documents",
    response_model=ApiResponse[CanvasDocumentRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    workspace_id: str,
    project_id: str,
    body: CanvasDocumentCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        row = await service.create_document(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            workflow_id=body.workflow_id,
            node_id=body.node_id,
            document=body.document,
            updated_by_user_id=LOCAL_USER_ID,
        )
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    return ApiResponse.ok(CanvasDocumentRead.model_validate(row))


@router.get(
    "/documents/{document_id}", response_model=ApiResponse[CanvasDocumentRead]
)
async def get_document(
    workspace_id: str,
    project_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        row = await service.get_document(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            document_id=document_id,
        )
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    return ApiResponse.ok(CanvasDocumentRead.model_validate(row))


@router.put(
    "/documents/{document_id}", response_model=ApiResponse[CanvasDocumentRead]
)
async def save_document(
    workspace_id: str,
    project_id: str,
    document_id: str,
    body: CanvasDocumentSave,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        document = await service.get_document(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            document_id=document_id,
        )
        row = await service.save_document(
            db,
            document=document,
            expected_revision=body.expected_revision,
            payload=body.document,
            updated_by_user_id=LOCAL_USER_ID,
        )
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    return ApiResponse.ok(CanvasDocumentRead.model_validate(row))


@router.post(
    "/documents/{document_id}/snapshots",
    response_model=ApiResponse[CanvasSnapshotRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_snapshot(
    workspace_id: str,
    project_id: str,
    document_id: str,
    body: CanvasSnapshotCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        document = await service.get_document(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            document_id=document_id,
        )
        row = await service.create_snapshot(
            db,
            document=document,
            expected_revision=body.expected_revision,
            executable_graph=body.executable_graph,
            model_fingerprint=body.model_fingerprint,
            seed=body.seed,
            lora_revisions=body.lora_revisions,
            asset_ids=body.asset_ids,
            created_by_user_id=LOCAL_USER_ID,
        )
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    return ApiResponse.ok(CanvasSnapshotRead.model_validate(row))


@router.post(
    "/media-assets/import",
    response_model=ApiResponse[MediaAssetRead],
    status_code=status.HTTP_201_CREATED,
)
async def import_asset(
    workspace_id: str,
    project_id: str,
    file: UploadFile = File(...),
    provenance: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        raw_provenance = json.loads(provenance)
        if not isinstance(raw_provenance, dict):
            raise service.MediaAssetValidationError("Asset provenance must be an object")
        payload = await file.read(service.MAX_MEDIA_ASSET_BYTES + 1)
        row = await service.import_asset_bytes(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            payload=payload,
            declared_mime_type=file.content_type,
            provenance=raw_provenance,
            filename=file.filename,
        )
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Asset provenance must be valid JSON"
        ) from exc
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    finally:
        await file.close()
    return ApiResponse.ok(MediaAssetRead.model_validate(row))


@router.get("/media-assets", response_model=ApiResponse[list[MediaAssetRead]])
async def list_assets(
    workspace_id: str,
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        rows = await service.list_assets(
            db, workspace_id=workspace_id, project_id=project_id
        )
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    return ApiResponse.ok([MediaAssetRead.model_validate(row) for row in rows])


@router.get("/media-assets/{asset_id}/content")
async def get_asset_content(
    workspace_id: str,
    project_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        asset = await service.get_asset(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_id=asset_id,
        )
        payload = await service.read_asset_content(asset)
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    return Response(
        content=payload,
        media_type=asset.mime_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(asset.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=60",
        },
    )


@router.get("/models", response_model=ApiResponse[list[ImageModelRead]])
async def list_models(
    workspace_id: str,
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        await service.require_project_scope(db, workspace_id, project_id)
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    settings = get_settings()
    if not settings.invokeai_enabled:
        return ApiResponse.ok([])
    client = InvokeAIClient(
        InvokeAIConnection(
            settings.invokeai_base_url,
            jwt=settings.invokeai_api_token or None,
            timeout_seconds=settings.invokeai_request_timeout_seconds,
        )
    )
    try:
        models_payload = await client.list_models()
        missing_payload = await client.list_missing_models()
    except InvokeAIClientError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Image model catalog is unavailable",
        ) from exc
    return ApiResponse.ok(
        [
            ImageModelRead.model_validate(item)
            for item in service.project_model_catalog(models_payload, missing_payload)
        ]
    )


@router.post(
    "/jobs",
    response_model=ApiResponse[ImageGenerationJobRead],
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_job(
    workspace_id: str,
    project_id: str,
    body: ImageGenerationJobCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        snapshot = await service.get_snapshot(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            snapshot_id=body.snapshot_id,
        )
        row = await service.create_job(
            db,
            snapshot=snapshot,
            run_id=body.run_id,
            node_id=body.node_id,
            attempt=body.attempt,
            idempotency_key=body.idempotency_key,
            mode=body.mode,
        )
        block_reason = dispatch_block_reason(get_settings())
        if block_reason is not None and row.status == ImageGenerationJobStatus.QUEUED.value:
            row = await service.transition_job(
                db,
                row,
                ImageGenerationJobStatus.BLOCKED,
                error_code=block_reason,
                error_detail=(
                    "Image generation requires the configured private runtime "
                    "and durable worker"
                ),
            )
        elif row.status in {
            ImageGenerationJobStatus.QUEUED.value,
            ImageGenerationJobStatus.SUBMITTED.value,
            ImageGenerationJobStatus.RUNNING.value,
            ImageGenerationJobStatus.INGESTING.value,
        }:
            # The task must never observe a job that the request transaction has
            # not committed yet. Duplicate deliveries are safe by job identity.
            await db.commit()
            from backend.worker.tasks import run_image_generation_job

            run_image_generation_job.delay(row.id)
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    return ApiResponse.ok(ImageGenerationJobRead.model_validate(row))


@router.get("/jobs/{job_id}", response_model=ApiResponse[ImageGenerationJobRead])
async def get_job(
    workspace_id: str,
    project_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        row = await service.get_job(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            job_id=job_id,
        )
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    return ApiResponse.ok(ImageGenerationJobRead.model_validate(row))


@router.get("/jobs/{job_id}/events")
async def stream_job_events(
    workspace_id: str,
    project_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    try:
        row = await service.get_job(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            job_id=job_id,
        )
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    public_job = ImageGenerationJobRead.model_validate(row).model_dump(
        mode="json", by_alias=True
    )

    async def events() -> AsyncIterator[str]:
        event = {"sequence": 1, "type": "status", "job": public_job}
        yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/jobs/{job_id}/cancel", response_model=ApiResponse[ImageGenerationJobRead]
)
async def cancel_job(
    workspace_id: str,
    project_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        row = await service.get_job(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            job_id=job_id,
        )
        if (
            row.invoke_queue_item_id
            and dispatch_block_reason(get_settings()) is None
            and row.status
            in {
                ImageGenerationJobStatus.SUBMITTED.value,
                ImageGenerationJobStatus.RUNNING.value,
                ImageGenerationJobStatus.INGESTING.value,
            }
        ):
            await db.commit()
            from backend.worker.tasks import cancel_image_generation_job

            cancel_image_generation_job.delay(row.id)
        else:
            row = await service.cancel_job(db, row)
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    return ApiResponse.ok(ImageGenerationJobRead.model_validate(row))


@router.post(
    "/jobs/{job_id}/retry-ingest", response_model=ApiResponse[ImageGenerationJobRead]
)
async def retry_job_ingest(
    workspace_id: str,
    project_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        row = await service.get_job(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            job_id=job_id,
        )
        if dispatch_block_reason(get_settings()) is not None:
            raise service.InvalidJobTransitionError(
                "Image asset ingest retry requires the configured durable worker"
            )
        row = await service.retry_ingest_job(db, row)
        await db.commit()
        from backend.worker.tasks import run_image_generation_job

        run_image_generation_job.delay(row.id)
    except service.ImageStudioError as exc:
        raise _translate_error(exc) from exc
    return ApiResponse.ok(ImageGenerationJobRead.model_validate(row))
