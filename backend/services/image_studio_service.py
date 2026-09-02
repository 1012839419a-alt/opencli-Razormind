"""Domain operations for OpenCLI-owned canvas documents, assets, and jobs."""

import asyncio
import hashlib
import os
import struct
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.image_studio import (
    CanvasDocument,
    CanvasSnapshot,
    ImageGenerationJob,
    ImageGenerationJobStatus,
    MediaAsset,
)
from backend.models.studio import StudioProject, StudioWorkflow, StudioWorkspace
from backend.models.workflow_run import WorkflowRun, WorkflowRunEvent
from backend.workflow.async_orchestrator import image_generation_execution_key


class ImageStudioError(Exception):
    pass


class ImageStudioNotFoundError(ImageStudioError):
    pass


class RevisionConflictError(ImageStudioError):
    pass


class ImageStudioConflictError(ImageStudioError):
    pass


class SnapshotValidationError(ImageStudioError):
    pass


def project_model_catalog(
    models_payload: dict,
    missing_payload: dict,
) -> list[dict[str, object]]:
    """Map the pinned Invoke model response to the stable public contract."""

    missing_models = missing_payload.get("models")
    missing_keys = {
        item.get("key")
        for item in missing_models
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    } if isinstance(missing_models, list) else set()
    models = models_payload.get("models")
    if not isinstance(models, list):
        return []

    catalog: list[dict[str, object]] = []
    for item in models:
        if not isinstance(item, dict) or item.get("type") != "main":
            continue
        key = item.get("key")
        name = item.get("name")
        fingerprint = item.get("hash")
        if not all(isinstance(value, str) and value for value in (key, name, fingerprint)):
            continue
        catalog.append(
            {
                "key": key,
                "name": name,
                "base": item.get("base") if isinstance(item.get("base"), str) else None,
                "type": "main",
                "fingerprint": fingerprint,
                "available": key not in missing_keys,
            }
        )
    return catalog


class MediaAssetValidationError(ImageStudioError):
    pass


class InvalidJobTransitionError(ImageStudioError):
    pass


_JOB_TRANSITIONS: dict[ImageGenerationJobStatus, set[ImageGenerationJobStatus]] = {
    ImageGenerationJobStatus.QUEUED: {
        ImageGenerationJobStatus.SUBMITTED,
        ImageGenerationJobStatus.BLOCKED,
        ImageGenerationJobStatus.FAILED,
        ImageGenerationJobStatus.CANCELLED,
        ImageGenerationJobStatus.TIMED_OUT,
    },
    ImageGenerationJobStatus.SUBMITTED: {
        ImageGenerationJobStatus.RUNNING,
        ImageGenerationJobStatus.BLOCKED,
        ImageGenerationJobStatus.FAILED,
        ImageGenerationJobStatus.CANCELLED,
        ImageGenerationJobStatus.TIMED_OUT,
    },
    ImageGenerationJobStatus.RUNNING: {
        ImageGenerationJobStatus.INGESTING,
        ImageGenerationJobStatus.BLOCKED,
        ImageGenerationJobStatus.FAILED,
        ImageGenerationJobStatus.CANCELLED,
        ImageGenerationJobStatus.TIMED_OUT,
    },
    ImageGenerationJobStatus.INGESTING: {
        ImageGenerationJobStatus.SUCCEEDED,
        ImageGenerationJobStatus.FAILED,
        ImageGenerationJobStatus.CANCELLED,
        ImageGenerationJobStatus.TIMED_OUT,
    },
    ImageGenerationJobStatus.BLOCKED: {
        ImageGenerationJobStatus.QUEUED,
        ImageGenerationJobStatus.CANCELLED,
        ImageGenerationJobStatus.FAILED,
        ImageGenerationJobStatus.TIMED_OUT,
    },
    ImageGenerationJobStatus.SUCCEEDED: set(),
    ImageGenerationJobStatus.FAILED: set(),
    ImageGenerationJobStatus.CANCELLED: set(),
    ImageGenerationJobStatus.TIMED_OUT: set(),
}

MAX_MEDIA_ASSET_BYTES = 20 * 1024 * 1024
MAX_MEDIA_ASSET_PIXELS = 40_000_000


def _media_root() -> Path:
    legacy_override = os.environ.get("OPENCLI_MEDIA_ROOT")
    return Path(legacy_override or get_settings().image_asset_storage_path).resolve()


def _strip_jpeg_app1(payload: bytes) -> bytes:
    output = bytearray(payload[:2])
    cursor = 2
    while cursor < len(payload):
        if payload[cursor] != 0xFF:
            return payload
        marker_start = cursor
        while cursor < len(payload) and payload[cursor] == 0xFF:
            cursor += 1
        if cursor >= len(payload):
            return payload
        marker = payload[cursor]
        cursor += 1
        if marker == 0xDA:
            output.extend(payload[marker_start:])
            return bytes(output)
        if marker in {0x01, *range(0xD0, 0xD9)}:
            output.extend(payload[marker_start:cursor])
            continue
        if cursor + 2 > len(payload):
            return payload
        segment_length = int.from_bytes(payload[cursor : cursor + 2], "big")
        segment_end = cursor + segment_length
        if segment_length < 2 or segment_end > len(payload):
            return payload
        if marker != 0xE1:
            output.extend(payload[marker_start:segment_end])
        cursor = segment_end
    return bytes(output)


def _strip_png_exif(payload: bytes) -> bytes:
    output = bytearray(payload[:8])
    cursor = 8
    while cursor + 12 <= len(payload):
        chunk_length = int.from_bytes(payload[cursor : cursor + 4], "big")
        chunk_end = cursor + 12 + chunk_length
        if chunk_end > len(payload):
            return payload
        if payload[cursor + 4 : cursor + 8] != b"eXIf":
            output.extend(payload[cursor:chunk_end])
        cursor = chunk_end
    return bytes(output) if cursor == len(payload) else payload


def _strip_webp_exif(payload: bytes) -> bytes:
    output = bytearray(b"RIFF\x00\x00\x00\x00WEBP")
    cursor = 12
    while cursor + 8 <= len(payload):
        chunk_type = payload[cursor : cursor + 4]
        chunk_length = int.from_bytes(payload[cursor + 4 : cursor + 8], "little")
        chunk_end = cursor + 8 + chunk_length + (chunk_length % 2)
        if chunk_end > len(payload):
            return payload
        if chunk_type != b"EXIF":
            output.extend(payload[cursor:chunk_end])
        cursor = chunk_end
    if cursor != len(payload):
        return payload
    output[4:8] = (len(output) - 8).to_bytes(4, "little")
    return bytes(output)


def _jpeg_dimensions(payload: bytes) -> tuple[int, int]:
    cursor = 2
    start_of_frame = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB}
    while cursor + 4 <= len(payload):
        if payload[cursor] != 0xFF:
            cursor += 1
            continue
        marker = payload[cursor + 1]
        cursor += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if cursor + 2 > len(payload):
            break
        segment_length = int.from_bytes(payload[cursor : cursor + 2], "big")
        if segment_length < 2 or cursor + segment_length > len(payload):
            break
        if marker in start_of_frame and segment_length >= 7:
            height = int.from_bytes(payload[cursor + 3 : cursor + 5], "big")
            width = int.from_bytes(payload[cursor + 5 : cursor + 7], "big")
            return width, height
        cursor += segment_length
    raise MediaAssetValidationError("JPEG dimensions could not be read")


def _webp_dimensions(payload: bytes) -> tuple[int, int]:
    chunk = payload[12:16]
    if chunk == b"VP8X" and len(payload) >= 30:
        width = 1 + int.from_bytes(payload[24:27], "little")
        height = 1 + int.from_bytes(payload[27:30], "little")
        return width, height
    if chunk == b"VP8L" and len(payload) >= 25 and payload[20] == 0x2F:
        bits = int.from_bytes(payload[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 " and len(payload) >= 30 and payload[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(payload[26:28], "little") & 0x3FFF
        height = int.from_bytes(payload[28:30], "little") & 0x3FFF
        return width, height
    raise MediaAssetValidationError("WebP dimensions could not be read")


def inspect_and_sanitize_image(payload: bytes) -> tuple[bytes, str, int, int, str]:
    if not payload:
        raise MediaAssetValidationError("Media asset is empty")
    if len(payload) > MAX_MEDIA_ASSET_BYTES:
        raise MediaAssetValidationError("Media asset exceeds the 20 MiB limit")
    if payload.startswith(b"\x89PNG\r\n\x1a\n") and len(payload) >= 24:
        sanitized = _strip_png_exif(payload)
        mime_type = "image/png"
        width, height = struct.unpack(">II", sanitized[16:24])
        extension = "png"
    elif payload.startswith(b"\xff\xd8"):
        sanitized = _strip_jpeg_app1(payload)
        mime_type = "image/jpeg"
        width, height = _jpeg_dimensions(sanitized)
        extension = "jpg"
    elif payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        sanitized = _strip_webp_exif(payload)
        mime_type = "image/webp"
        width, height = _webp_dimensions(sanitized)
        extension = "webp"
    else:
        raise MediaAssetValidationError("Unsupported media asset type")
    if width <= 0 or height <= 0 or width * height > MAX_MEDIA_ASSET_PIXELS:
        raise MediaAssetValidationError("Media asset dimensions exceed platform limits")
    return sanitized, mime_type, width, height, extension


def _safe_filename(value: str | None, extension: str) -> str:
    leaf = Path(value or f"asset.{extension}").name
    cleaned = "".join(character for character in leaf if ord(character) >= 32).strip()
    return (cleaned or f"asset.{extension}")[:255]


async def require_project_scope(
    db: AsyncSession, workspace_id: str, project_id: str
) -> StudioProject:
    workspace = await db.scalar(
        select(StudioWorkspace.id).where(
            StudioWorkspace.id == workspace_id,
            StudioWorkspace.active.is_(True),
        )
    )
    if workspace is None:
        raise ImageStudioNotFoundError("Workspace not found")
    project = await db.scalar(
        select(StudioProject).where(
            StudioProject.id == project_id,
            StudioProject.workspace_id == workspace_id,
            StudioProject.archived.is_(False),
        )
    )
    if project is None:
        raise ImageStudioNotFoundError("Project not found")
    return project


async def require_workflow_scope(
    db: AsyncSession, workspace_id: str, project_id: str, workflow_id: str
) -> StudioWorkflow:
    await require_project_scope(db, workspace_id, project_id)
    workflow = await db.scalar(
        select(StudioWorkflow).where(
            StudioWorkflow.id == workflow_id,
            StudioWorkflow.project_id == project_id,
            StudioWorkflow.archived.is_(False),
        )
    )
    if workflow is None:
        raise ImageStudioNotFoundError("Workflow not found")
    return workflow


async def create_document(
    db: AsyncSession,
    *,
    workspace_id: str,
    project_id: str,
    workflow_id: str,
    node_id: str,
    document: dict,
    updated_by_user_id: str,
) -> CanvasDocument:
    await require_workflow_scope(db, workspace_id, project_id, workflow_id)
    existing = await db.scalar(
        select(CanvasDocument.id).where(
            CanvasDocument.workspace_id == workspace_id,
            CanvasDocument.project_id == project_id,
            CanvasDocument.workflow_id == workflow_id,
            CanvasDocument.node_id == node_id,
        )
    )
    if existing is not None:
        raise ImageStudioConflictError("Canvas document already exists for workflow node")
    row = CanvasDocument(
        workspace_id=workspace_id,
        project_id=project_id,
        workflow_id=workflow_id,
        node_id=node_id,
        revision=1,
        document=deepcopy(document),
        updated_by_user_id=updated_by_user_id,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ImageStudioConflictError(
            "Canvas document already exists for workflow node"
        ) from exc
    return row


async def get_document(
    db: AsyncSession,
    *,
    workspace_id: str,
    project_id: str,
    document_id: str,
) -> CanvasDocument:
    await require_project_scope(db, workspace_id, project_id)
    row = await db.scalar(
        select(CanvasDocument).where(
            CanvasDocument.id == document_id,
            CanvasDocument.workspace_id == workspace_id,
            CanvasDocument.project_id == project_id,
        )
    )
    if row is None:
        raise ImageStudioNotFoundError("Canvas document not found")
    return row


async def save_document(
    db: AsyncSession,
    *,
    document: CanvasDocument,
    expected_revision: int,
    payload: dict,
    updated_by_user_id: str,
) -> CanvasDocument:
    result = await db.execute(
        update(CanvasDocument)
        .where(
            CanvasDocument.id == document.id,
            CanvasDocument.revision == expected_revision,
        )
        .values(
            revision=CanvasDocument.revision + 1,
            document=deepcopy(payload),
            updated_by_user_id=updated_by_user_id,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise RevisionConflictError("Canvas document revision conflict")
    await db.flush()
    await db.refresh(document)
    return document


async def create_snapshot(
    db: AsyncSession,
    *,
    document: CanvasDocument,
    expected_revision: int,
    executable_graph: dict,
    model_fingerprint: str,
    seed: int,
    lora_revisions: list[dict],
    asset_ids: list[str],
    created_by_user_id: str,
) -> CanvasSnapshot:
    await db.refresh(document)
    if document.revision != expected_revision:
        raise RevisionConflictError("Canvas document revision conflict")
    unique_asset_ids = list(dict.fromkeys(asset_ids))
    if unique_asset_ids:
        owned_assets = (
            (
                await db.execute(
                    select(MediaAsset.id).where(
                        MediaAsset.id.in_(unique_asset_ids),
                        MediaAsset.workspace_id == document.workspace_id,
                        MediaAsset.project_id == document.project_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        if set(owned_assets) != set(unique_asset_ids):
            raise SnapshotValidationError("Snapshot contains unavailable media assets")
    row = CanvasSnapshot(
        workspace_id=document.workspace_id,
        project_id=document.project_id,
        workflow_id=document.workflow_id,
        node_id=document.node_id,
        document_id=document.id,
        document_revision=document.revision,
        canvas_document=deepcopy(document.document),
        executable_graph=deepcopy(executable_graph),
        model_fingerprint=model_fingerprint,
        seed=seed,
        lora_revisions=deepcopy(lora_revisions),
        asset_ids=unique_asset_ids,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    await db.flush()
    return row


async def get_snapshot(
    db: AsyncSession,
    *,
    workspace_id: str,
    project_id: str,
    snapshot_id: str,
) -> CanvasSnapshot:
    row = await db.scalar(
        select(CanvasSnapshot).where(
            CanvasSnapshot.id == snapshot_id,
            CanvasSnapshot.workspace_id == workspace_id,
            CanvasSnapshot.project_id == project_id,
        )
    )
    if row is None:
        raise ImageStudioNotFoundError("Canvas snapshot not found")
    return row


async def import_asset(
    db: AsyncSession,
    *,
    workspace_id: str,
    project_id: str,
    sha256: str,
    width: int,
    height: int,
    mime_type: str,
    storage_key: str,
    provenance: dict,
    filename: str | None = None,
) -> MediaAsset:
    await require_project_scope(db, workspace_id, project_id)
    existing = await db.scalar(
        select(MediaAsset).where(
            MediaAsset.workspace_id == workspace_id,
            MediaAsset.project_id == project_id,
            MediaAsset.sha256 == sha256,
        )
    )
    if existing is not None:
        return existing
    row = MediaAsset(
        workspace_id=workspace_id,
        project_id=project_id,
        sha256=sha256,
        width=width,
        height=height,
        mime_type=mime_type,
        filename=_safe_filename(filename, mime_type.rsplit("/", 1)[-1]),
        storage_key=storage_key,
        provenance=deepcopy(provenance),
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ImageStudioConflictError("Media asset storage key already exists") from exc
    return row


def _io_path(path: Path) -> Path:
    if os.name != "nt":
        return path

    absolute = str(path.resolve())
    if absolute.startswith("\\\\?\\"):
        return path
    if absolute.startswith("\\\\"):
        return Path(f"\\\\?\\UNC\\{absolute[2:]}")
    return Path(f"\\\\?\\{absolute}")


def _persist_media_asset(destination: Path, payload: bytes) -> None:
    destination = _io_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return

    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        try:
            temporary.replace(destination)
        except OSError:
            # Another writer may have won the same content-addressed path.
            if not destination.is_file():
                raise
    finally:
        temporary.unlink(missing_ok=True)


async def import_asset_bytes(
    db: AsyncSession,
    *,
    workspace_id: str,
    project_id: str,
    payload: bytes,
    declared_mime_type: str | None,
    provenance: dict,
    filename: str | None = None,
) -> MediaAsset:
    await require_project_scope(db, workspace_id, project_id)
    sanitized, mime_type, width, height, extension = inspect_and_sanitize_image(payload)
    if declared_mime_type and declared_mime_type != mime_type:
        raise MediaAssetValidationError("Declared media type does not match file content")
    sha256 = hashlib.sha256(sanitized).hexdigest()
    media_root = _media_root()
    relative_key = (
        Path("workspaces")
        / workspace_id
        / "projects"
        / project_id
        / f"{sha256}.{extension}"
    )
    destination = media_root / relative_key

    await asyncio.to_thread(_persist_media_asset, destination, sanitized)
    return await import_asset(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        sha256=sha256,
        width=width,
        height=height,
        mime_type=mime_type,
        storage_key=relative_key.as_posix(),
        provenance=provenance,
        filename=_safe_filename(filename, extension),
    )


async def get_asset(
    db: AsyncSession,
    *,
    workspace_id: str,
    project_id: str,
    asset_id: str,
) -> MediaAsset:
    await require_project_scope(db, workspace_id, project_id)
    row = await db.scalar(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.workspace_id == workspace_id,
            MediaAsset.project_id == project_id,
        )
    )
    if row is None:
        raise ImageStudioNotFoundError("Media asset not found")
    return row


async def read_asset_content(asset: MediaAsset) -> bytes:
    media_root = _media_root()
    path = (media_root / asset.storage_key).resolve()
    try:
        path.relative_to(media_root)
    except ValueError as exc:
        raise MediaAssetValidationError("Media asset storage key is invalid") from exc
    io_path = _io_path(path)
    if not io_path.is_file():
        raise ImageStudioNotFoundError("Media asset content not found")
    return await asyncio.to_thread(io_path.read_bytes)


async def list_assets(
    db: AsyncSession, *, workspace_id: str, project_id: str
) -> list[MediaAsset]:
    await require_project_scope(db, workspace_id, project_id)
    result = await db.execute(
        select(MediaAsset)
        .where(
            MediaAsset.workspace_id == workspace_id,
            MediaAsset.project_id == project_id,
        )
        .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
    )
    return list(result.scalars().all())


async def require_waiting_run_binding(
    db: AsyncSession,
    *,
    snapshot: CanvasSnapshot,
    run_id: str,
    node_id: str,
    attempt: int,
    idempotency_key: str,
    job_id: str | None = None,
    lock_run: bool = False,
) -> WorkflowRun:
    """Require one generation identity to match the persisted waiting checkpoint."""

    await require_workflow_scope(
        db,
        snapshot.workspace_id,
        snapshot.project_id,
        snapshot.workflow_id,
    )
    statement = select(WorkflowRun).where(WorkflowRun.id == run_id)
    if lock_run:
        statement = statement.with_for_update()
    workflow_run = await db.scalar(statement)
    if workflow_run is None or workflow_run.workflow_id != snapshot.workflow_id:
        raise ImageStudioNotFoundError("Workflow run not found")

    projection = workflow_run.projection if isinstance(workflow_run.projection, dict) else {}
    node_states = projection.get("nodeStates", [])
    node_is_waiting = any(
        isinstance(state, dict)
        and state.get("nodeId") == node_id
        and state.get("status") == "waiting"
        for state in node_states
    )
    if (
        workflow_run.status != "waiting"
        or projection.get("status") != "waiting"
        or not node_is_waiting
    ):
        raise ImageStudioConflictError("Workflow run node is not waiting")

    execution_key = image_generation_execution_key(run_id, node_id, attempt)
    if idempotency_key != execution_key.idempotency_key:
        raise ImageStudioConflictError(
            "Idempotency key does not match the workflow checkpoint"
        )
    if job_id is not None and job_id != execution_key.job_id:
        raise ImageStudioConflictError("Job does not match the workflow checkpoint")

    waiting_event = await db.scalar(
        select(WorkflowRunEvent)
        .where(
            WorkflowRunEvent.run_id == run_id,
            WorkflowRunEvent.workflow_id == snapshot.workflow_id,
            WorkflowRunEvent.node_id == node_id,
            WorkflowRunEvent.event_type == "waiting",
        )
        .order_by(WorkflowRunEvent.sequence.desc())
        .limit(1)
    )
    details = (
        waiting_event.payload.get("details", {})
        if waiting_event is not None and isinstance(waiting_event.payload, dict)
        else {}
    )
    expected_details = {
        **execution_key.as_details(),
        "canvasSnapshotId": snapshot.id,
    }
    if any(details.get(key) != value for key, value in expected_details.items()):
        raise ImageStudioConflictError(
            "Image generation does not match the workflow checkpoint"
        )
    return workflow_run


async def create_job(
    db: AsyncSession,
    *,
    snapshot: CanvasSnapshot,
    run_id: str,
    node_id: str,
    attempt: int,
    idempotency_key: str,
    mode: str = "workflow",
) -> ImageGenerationJob:
    if node_id != snapshot.node_id:
        raise SnapshotValidationError("Job node does not match snapshot node")
    is_preview = mode == "preview"
    if is_preview:
        await require_workflow_scope(
            db,
            snapshot.workspace_id,
            snapshot.project_id,
            snapshot.workflow_id,
        )
        if run_id != snapshot.id or attempt != 1:
            raise ImageStudioConflictError(
                "Preview job identity does not match the canvas snapshot"
            )
        execution_key = None
    else:
        execution_key = image_generation_execution_key(run_id, node_id, attempt)
        await require_waiting_run_binding(
            db,
            snapshot=snapshot,
            run_id=run_id,
            node_id=node_id,
            attempt=attempt,
            idempotency_key=idempotency_key,
            job_id=execution_key.job_id,
        )
    existing = await db.scalar(
        select(ImageGenerationJob).where(
            ImageGenerationJob.workspace_id == snapshot.workspace_id,
            ImageGenerationJob.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if (
            existing.snapshot_id != snapshot.id
            or existing.run_id != run_id
            or existing.node_id != node_id
            or existing.attempt != attempt
        ):
            raise ImageStudioConflictError(
                "Idempotency key is bound to another generation"
            )
        return existing
    execution_duplicate = await db.scalar(
        select(ImageGenerationJob).where(
            ImageGenerationJob.workspace_id == snapshot.workspace_id,
            ImageGenerationJob.run_id == run_id,
            ImageGenerationJob.node_id == node_id,
            ImageGenerationJob.attempt == attempt,
        )
    )
    if execution_duplicate is not None:
        raise ImageStudioConflictError(
            "Workflow run node attempt is already bound to another generation"
        )
    row = ImageGenerationJob(
        workspace_id=snapshot.workspace_id,
        project_id=snapshot.project_id,
        workflow_id=snapshot.workflow_id,
        run_id=run_id,
        node_id=node_id,
        attempt=attempt,
        snapshot_id=snapshot.id,
        idempotency_key=idempotency_key,
        status=ImageGenerationJobStatus.QUEUED.value,
    )
    if execution_key is not None:
        row.id = execution_key.job_id
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ImageStudioConflictError(
            "Image generation idempotency key already exists"
        ) from exc
    return row


async def prepare_workflow_image_resume(
    db: AsyncSession,
    *,
    job_id: str,
    run_id: str,
    node_id: str,
    assets: list[dict],
) -> list[dict] | None:
    """Validate a completed job and rebuild the downstream payload from owned assets.

    Preview jobs intentionally return ``None`` because they are authoring-only
    and must never continue a WorkflowRun.
    """

    job = await db.scalar(
        select(ImageGenerationJob)
        .where(ImageGenerationJob.id == job_id)
        .with_for_update()
    )
    if job is None:
        raise ImageStudioNotFoundError("Image generation job not found")
    if job.run_id != run_id or job.node_id != node_id:
        raise ImageStudioConflictError("Resume task does not match the image job")
    if job.status != ImageGenerationJobStatus.SUCCEEDED.value:
        raise ImageStudioConflictError("Image generation job is not complete")

    snapshot = await db.scalar(
        select(CanvasSnapshot).where(
            CanvasSnapshot.id == job.snapshot_id,
            CanvasSnapshot.workspace_id == job.workspace_id,
            CanvasSnapshot.project_id == job.project_id,
            CanvasSnapshot.workflow_id == job.workflow_id,
            CanvasSnapshot.node_id == job.node_id,
        )
    )
    if snapshot is None:
        raise ImageStudioNotFoundError("Canvas snapshot not found")
    if job.run_id == snapshot.id:
        return None

    await require_waiting_run_binding(
        db,
        snapshot=snapshot,
        run_id=job.run_id,
        node_id=job.node_id,
        attempt=job.attempt,
        idempotency_key=job.idempotency_key,
        job_id=job.id,
        lock_run=True,
    )

    incoming_asset_ids = [
        asset.get("id") if isinstance(asset, dict) else None for asset in assets
    ]
    output_asset_ids = list(job.output_asset_ids or [])
    if incoming_asset_ids != output_asset_ids:
        raise ImageStudioConflictError("Resume assets do not match the image job")
    if not output_asset_ids:
        return []

    rows = (
        await db.execute(
            select(MediaAsset).where(
                MediaAsset.id.in_(output_asset_ids),
                MediaAsset.workspace_id == job.workspace_id,
                MediaAsset.project_id == job.project_id,
            )
        )
    ).scalars().all()
    by_id = {asset.id: asset for asset in rows}
    if any(asset_id not in by_id for asset_id in output_asset_ids):
        raise ImageStudioNotFoundError("Image generation output asset not found")
    return [
        {
            "id": by_id[asset_id].id,
            "type": "mediaAsset",
            "mimeType": by_id[asset_id].mime_type,
            "width": by_id[asset_id].width,
            "height": by_id[asset_id].height,
            "contentUrl": by_id[asset_id].content_url,
            "provenance": dict(by_id[asset_id].provenance or {}),
        }
        for asset_id in output_asset_ids
    ]


async def get_job(
    db: AsyncSession,
    *,
    workspace_id: str,
    project_id: str,
    job_id: str,
) -> ImageGenerationJob:
    row = await db.scalar(
        select(ImageGenerationJob).where(
            ImageGenerationJob.id == job_id,
            ImageGenerationJob.workspace_id == workspace_id,
            ImageGenerationJob.project_id == project_id,
        )
    )
    if row is None:
        raise ImageStudioNotFoundError("Image generation job not found")
    return row


async def transition_job(
    db: AsyncSession,
    job: ImageGenerationJob,
    target: ImageGenerationJobStatus,
    *,
    error_code: str | None = None,
    error_detail: str | None = None,
    output_asset_ids: list[str] | None = None,
) -> ImageGenerationJob:
    current = ImageGenerationJobStatus(job.status)
    if target not in _JOB_TRANSITIONS[current]:
        raise InvalidJobTransitionError(
            f"Cannot transition image job from {current} to {target}"
        )
    job.status = target.value
    job.error_code = error_code
    job.error_detail = error_detail
    if output_asset_ids is not None:
        job.output_asset_ids = list(output_asset_ids)
    await db.flush()
    return job


async def cancel_job(db: AsyncSession, job: ImageGenerationJob) -> ImageGenerationJob:
    if job.status == ImageGenerationJobStatus.CANCELLED.value:
        return job
    return await transition_job(db, job, ImageGenerationJobStatus.CANCELLED)


async def retry_ingest_job(
    db: AsyncSession, job: ImageGenerationJob
) -> ImageGenerationJob:
    """Reopen only a storage-ingest failure without regenerating an image."""

    if (
        job.status != ImageGenerationJobStatus.FAILED.value
        or job.error_code != "retryable-ingest"
        or not job.invoke_queue_item_id
    ):
        raise InvalidJobTransitionError("Image job is not retryable at asset ingest")
    job.status = ImageGenerationJobStatus.INGESTING.value
    job.error_code = None
    job.error_detail = None
    await db.flush()
    return job
