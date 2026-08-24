"""Reusable, credential-owning delivery destinations."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.auth import crypto
from backend.models.base import TimestampMixin


class DeliveryConnection(TimestampMixin):
    __tablename__ = "delivery_connections"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="feishu_bitable")
    app_id: Mapped[str] = mapped_column(String(255), nullable=False)
    _app_secret_encrypted: Mapped[str | None] = mapped_column("app_secret", Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    @property
    def app_secret(self) -> str | None:
        value = self._app_secret_encrypted
        return crypto.decrypt(value) if value else value

    @app_secret.setter
    def app_secret(self, value: str | None) -> None:
        self._app_secret_encrypted = crypto.encrypt(value) if value else value


class DeliveryAttempt(TimestampMixin):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "app_token",
            "table_id",
            "record_id",
            name="uq_delivery_attempt_target_record",
        ),
    )

    connection_id: Mapped[str] = mapped_column(
        ForeignKey("delivery_connections.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    app_token: Mapped[str] = mapped_column(String(255), nullable=False)
    table_id: Mapped[str] = mapped_column(String(255), nullable=False)
    record_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    evidence_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    remote_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(96), nullable=True)
    field_map: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
