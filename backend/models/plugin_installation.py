"""Persisted metadata for installed plugin packages."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import TimestampMixin


class PluginInstallation(TimestampMixin):
    __tablename__ = "plugin_installations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "provider_key",
            "version",
            "source_digest",
            name="uq_plugin_installations_workspace_provider_version_digest",
        ),
    )

    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    granted_permissions_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    provider_key: Mapped[str] = mapped_column(String(257), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    author: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_spec_version: Mapped[str] = mapped_column(String(32), nullable=False)
    signature_state: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    capabilities_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    permissions_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    runtime_status: Mapped[str] = mapped_column(String(32), nullable=False)
    blockers_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
