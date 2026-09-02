from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.schemas.common import UTCModel


class AgentConversationCreate(BaseModel):
    workspace_id: str | None = Field(default=None, min_length=1, max_length=36)
    title: str | None = Field(default=None, max_length=255)
    context: dict[str, Any] | None = None


class AgentConversationMessageCreate(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=20_000)
    context: dict[str, Any] | None = None


class AgentConversationTurnRead(UTCModel):
    id: str
    sequence: int
    request_id: str
    user_content: str
    response: dict[str, Any] | None
    context_binding: dict[str, Any]
    tool_trace: list[dict[str, Any]]
    status: str
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentConversationRead(UTCModel):
    id: str
    workspace_id: str
    title: str | None
    status: str
    created_by_user_id: str
    context_binding: dict[str, Any]
    revision: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentConversationDetail(AgentConversationRead):
    turns: list[AgentConversationTurnRead] = Field(default_factory=list)


class AgentConversationMessageRead(UTCModel):
    conversation_id: str
    turn: AgentConversationTurnRead
