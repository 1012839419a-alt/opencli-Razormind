"""Request and response schemas for Studio collaboration service callbacks."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class CollaborationRoomRequest(BaseModel):
    room: str = Field(min_length=1, max_length=512)


class CollaborationRoomRead(BaseModel):
    room: str


class YMapJSON(BaseModel):
    """JSON representation emitted by ``Y.Map.toJSON()``."""

    type: Literal["Map"]
    content: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CollaborationSnapshotData(BaseModel):
    nodes: YMapJSON
    edges: YMapJSON


class CollaborationSnapshotRequest(CollaborationRoomRequest):
    data: CollaborationSnapshotData


class CollaborationSnapshotRead(BaseModel):
    revision: int
