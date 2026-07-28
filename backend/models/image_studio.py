"""Authoritative OpenCLI records for the first-party image studio."""

from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import TimestampMixin


class ImageGenerationJobStatus(StrEnum):
    QUEUED = "queued"
    SUBMITTED = "submitted"
    RUNNING = "running"
    INGESTING = "ingesting"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class CanvasDocument(TimestampMixin):
    __tablename__ = "canvas_documents"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "project_id",
            "workflow_id",
            "node_id",
            name="uq_canvas_document_workflow_node",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("studio_workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("studio_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    document: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_by_user_id: Mapped[str] = mapped_column(String(100), nullable=False)


class CanvasSnapshot(TimestampMixin):
    __tablename__ = "canvas_snapshots"

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("studio_workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("studio_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("canvas_documents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    canvas_document: Mapped[dict] = mapped_column(JSON, nullable=False)
    executable_graph: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lora_revisions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    asset_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by_user_id: Mapped[str] = mapped_column(String(100), nullable=False)


class MediaAsset(TimestampMixin):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "project_id", "sha256", name="uq_media_asset_project_sha256"
        ),
        CheckConstraint("width > 0", name="ck_media_assets_width_positive"),
        CheckConstraint("height > 0", name="ck_media_assets_height_positive"),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("studio_workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    @property
    def content_url(self) -> str:
        return (
            f"/api/v1/workspaces/{self.workspace_id}/projects/{self.project_id}"
            f"/image-studio/media-assets/{self.id}/content"
        )


class ImageGenerationJob(TimestampMixin):
    __tablename__ = "image_generation_jobs"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_image_generation_job_idempotency"
        ),
        UniqueConstraint(
            "workspace_id",
            "run_id",
            "node_id",
            "attempt",
            name="uq_image_generation_job_run_node_attempt",
        ),
        CheckConstraint(
            "status IN ('queued', 'submitted', 'running', 'ingesting', 'succeeded', "
            "'blocked', 'failed', 'cancelled', 'timed_out')",
            name="ck_image_generation_jobs_status",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("studio_workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("studio_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("canvas_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ImageGenerationJobStatus.QUEUED.value
    )
    invoke_batch_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoke_queue_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoke_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_asset_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
