"""Authenticated durable-session API for the Global Agent Dock."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.v1.chat import (
    ChatMessage,
    ChatRequest,
    _build_client,
    _chat_with_client,
    _pick_provider,
)
from backend.control.agent_control import agent_control_service
from backend.database import get_db
from backend.models.agent_conversation import AgentConversation, AgentConversationTurn
from backend.schemas.common import ApiResponse
from backend.security.identity import RequestIdentity, get_request_identity
from backend.services import agent_conversation_service as conversations

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat/sessions", tags=["agent-conversations"])


class SessionCreate(BaseModel):
    workspace_id: str | None = None
    title: str | None = Field(default=None, max_length=255)
    context: dict[str, Any] = Field(default_factory=dict)


class SessionMessageCreate(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=20_000)
    context: dict[str, Any] = Field(default_factory=dict)


def _session_data(conversation: AgentConversation) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "workspace_id": conversation.workspace_id,
        "title": conversation.title,
        "status": conversation.status,
        "context_binding": conversation.context_binding,
        "revision": conversation.revision,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def _turn_data(turn: AgentConversationTurn) -> dict[str, Any]:
    return {
        "sequence": turn.sequence,
        "request_id": turn.request_id,
        "status": turn.status,
        "user_content": turn.user_content,
        "response": turn.response,
        "context_binding": turn.context_binding,
        "tool_trace": turn.tool_trace,
        "error_code": turn.error_code,
        "error_message": turn.error_message,
        "created_at": turn.created_at,
        "updated_at": turn.updated_at,
    }


@router.post("", response_model=ApiResponse[dict[str, Any]], status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    workspace_id = await agent_control_service.resolve_workspace_id(db, identity, body.workspace_id)
    conversation = await conversations.create_conversation(
        db,
        workspace_id=workspace_id,
        identity=identity,
        title=body.title,
        context=body.context,
    )
    return ApiResponse.ok(
        {"conversation_id": conversation.id, "session": _session_data(conversation)}
    )


@router.get("", response_model=ApiResponse[list[dict[str, Any]]])
async def list_sessions(
    workspace_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    rows = await conversations.list_conversations(
        db, workspace_id=workspace_id, identity=identity, limit=limit
    )
    return ApiResponse.ok([_session_data(row) for row in rows])


@router.get("/{conversation_id}", response_model=ApiResponse[dict[str, Any]])
async def get_session(
    conversation_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=50),
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    conversation, _ = await conversations.get_readable_conversation(db, conversation_id, identity)
    turns = await conversations.list_turns(
        db, conversation, after_sequence=after_sequence, limit=limit
    )
    return ApiResponse.ok(
        {**_session_data(conversation), "turns": [_turn_data(turn) for turn in turns]}
    )


@router.post("/{conversation_id}/messages", response_model=ApiResponse[dict[str, Any]])
async def send_message(
    conversation_id: str,
    body: SessionMessageCreate,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    conversation, _ = await conversations.get_readable_conversation(db, conversation_id, identity)
    turn, created = await conversations.begin_turn(
        db,
        conversation=conversation,
        request_id=body.request_id,
        content=body.content,
        context=body.context,
    )
    if not created:
        return ApiResponse.ok({"conversation_id": conversation.id, "turn": _turn_data(turn)})

    # The turn is durable before the slow provider call, so a restart can replay
    # the in-flight state and no model call holds an open database transaction.
    await db.commit()
    try:
        provider = await _pick_provider(db, None)
        client = await _build_client(provider)
        model = provider.default_model or "gpt-4o-mini"
        messages = await conversations.history_messages(db, conversation.id, turn)
        context = {**turn.context_binding, "workspace_id": conversation.workspace_id}
        system = "你是 opencli-admin 的全局操作助手。用中文简洁回答。"
        if context:
            import json

            system += f"\n\n当前用户操作上下文 (JSON): {json.dumps(context, ensure_ascii=False)}"
        execution = await _chat_with_client(
            client,
            model,
            system,
            ChatRequest(messages=[ChatMessage(**message) for message in messages], context=context),
            db,
            identity,
        )
        turn = await conversations.complete_turn(
            db, turn, execution.reply.model_dump(exclude_none=True), execution.tool_trace
        )
        await db.commit()
    except HTTPException as exc:
        # Provider and tool-loop failures receive a durable, non-secret failure state.
        turn = await conversations.fail_turn(db, turn, f"http_{exc.status_code}")
        await db.commit()
        raise
    except Exception as exc:
        logger.exception(
            "agent conversation model execution failed conversation=%s", conversation.id
        )
        turn = await conversations.fail_turn(db, turn, "model_execution_failed")
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "model request failed") from exc
    return ApiResponse.ok({"conversation_id": conversation.id, "turn": _turn_data(turn)})


@router.post("/{conversation_id}/close", response_model=ApiResponse[dict[str, Any]])
async def close_session(
    conversation_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    conversation, access = await conversations.get_readable_conversation(
        db, conversation_id, identity
    )
    conversation = await conversations.close_conversation(db, conversation, access)
    return ApiResponse.ok(_session_data(conversation))
