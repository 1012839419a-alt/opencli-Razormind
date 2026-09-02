from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from backend.schemas.common import UTCModel


class TaskTriggerRequest(BaseModel):
    source_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=1, le=10)
    agent_id: Optional[str] = None


class TaskRecoveryRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    reason: str = Field(..., min_length=1, max_length=2000)
    mode: Literal["recollect"] = "recollect"
    initiating_actor: str = Field(default="operator", min_length=1, max_length=255)


class TaskRecoveryRead(BaseModel):
    task_id: str
    retry_of_task_id: str
    status: str
    recovery_mode: str
    idempotency_replayed: bool = False


class CollectionTaskRead(UTCModel):
    id: str
    source_id: str
    source_name: Optional[str] = None
    agent_id: Optional[str] = None
    trigger_type: str
    parameters: dict[str, Any]
    priority: int
    status: str
    error_message: Optional[str] = None
    retry_of_task_id: Optional[str] = None
    recovery_mode: Optional[str] = None
    recovery_reason: Optional[str] = None
    initiating_actor: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskRunRead(UTCModel):
    id: str
    task_id: str
    status: str
    worker_id: Optional[str]
    celery_task_id: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    records_collected: int
    error_message: Optional[str]
    error_detail: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}
