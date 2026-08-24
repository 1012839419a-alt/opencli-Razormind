from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from backend.schemas.common import UTCModel


class DeliveryConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    app_id: str = Field(min_length=1, max_length=255)
    app_secret: str = Field(min_length=1, max_length=4096)
    enabled: bool = True


class DeliveryConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    app_id: str | None = Field(default=None, min_length=1, max_length=255)
    app_secret: str | None = Field(default=None, min_length=1, max_length=4096)
    enabled: bool | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> DeliveryConnectionUpdate:
        nullable_updates = {"name", "app_id", "app_secret", "enabled"}
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in nullable_updates
        ):
            raise ValueError("delivery connection fields cannot be null")
        return self


class DeliveryConnectionRead(UTCModel):
    id: str
    name: str
    provider: str
    app_id_preview: str
    has_app_secret: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, row: Any) -> DeliveryConnectionRead:
        app_id = row.app_id
        return cls(
            id=row.id,
            name=row.name,
            provider=row.provider,
            app_id_preview=(f"...{app_id[-4:]}" if len(app_id) >= 4 else "...."),
            has_app_secret=bool(row._app_secret_encrypted),
            enabled=row.enabled,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class FeishuBitableTargetProbe(BaseModel):
    app_token: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_-]+$")
    table_id: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_-]+$")


class FeishuBitableTargetConfig(FeishuBitableTargetProbe):
    connection_id: str = Field(min_length=1, max_length=36)
    field_map: dict[str, str] = Field(default_factory=dict)
