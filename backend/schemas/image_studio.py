"""Stable platform schemas exposed to the first-party ImageStudio host."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ImageStudioModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class CanvasDocumentCreate(ImageStudioModel):
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1, max_length=255)
    document: dict[str, Any] = Field(
        default_factory=lambda: {"version": 1, "layers": [], "settings": {}}
    )


class CanvasDocumentSave(ImageStudioModel):
    expected_revision: int = Field(ge=1)
    document: dict[str, Any]


class CanvasDocumentRead(ImageStudioModel):
    id: str
    workspace_id: str
    project_id: str
    workflow_id: str
    node_id: str
    revision: int
    document: dict[str, Any]
    updated_by_user_id: str
    created_at: datetime
    updated_at: datetime


class CanvasSnapshotCreate(ImageStudioModel):
    expected_revision: int = Field(ge=1)
    executable_graph: dict[str, Any]
    model_fingerprint: str = Field(min_length=1, max_length=255)
    seed: int = Field(ge=0)
    lora_revisions: list[dict[str, Any]] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)


class CanvasSnapshotRead(ImageStudioModel):
    id: str
    workspace_id: str
    project_id: str
    workflow_id: str
    node_id: str
    document_id: str
    document_revision: int
    canvas_document: dict[str, Any]
    executable_graph: dict[str, Any]
    model_fingerprint: str
    seed: int
    lora_revisions: list[dict[str, Any]]
    asset_ids: list[str]
    created_by_user_id: str
    created_at: datetime


class MediaAssetImport(ImageStudioModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    storage_key: str = Field(min_length=1, max_length=1024)
    provenance: dict[str, Any] = Field(default_factory=dict)


class MediaAssetRead(ImageStudioModel):
    id: str
    workspace_id: str
    project_id: str
    sha256: str
    width: int
    height: int
    mime_type: str
    filename: str
    content_url: str
    provenance: dict[str, Any]
    created_at: datetime


ImageGenerationStatus = Literal[
    "queued",
    "submitted",
    "running",
    "ingesting",
    "succeeded",
    "blocked",
    "failed",
    "cancelled",
    "timed_out",
]


class ImageGenerationJobCreate(ImageStudioModel):
    mode: Literal["workflow", "preview"] = "workflow"
    snapshot_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1, max_length=36)
    node_id: str = Field(min_length=1, max_length=255)
    attempt: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=512)


class ImageGenerationJobRead(ImageStudioModel):
    id: str
    workspace_id: str
    project_id: str
    workflow_id: str
    run_id: str
    node_id: str
    attempt: int
    snapshot_id: str
    idempotency_key: str
    status: ImageGenerationStatus
    invoke_batch_id: str | None
    invoke_queue_item_id: str | None
    invoke_session_id: str | None
    output_asset_ids: list[str]
    error_code: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime


class ImageModelRead(ImageStudioModel):
    key: str
    name: str
    base: str | None = None
    type: str
    fingerprint: str
    available: bool
