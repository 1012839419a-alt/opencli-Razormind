"""Session lifecycle and safe persistence helpers for the Global Agent Dock."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_conversation import AgentConversation, AgentConversationTurn
from backend.models.source_binding import Source
from backend.models.workflow import Project, Workflow
from backend.models.workflow_run import WorkflowRun
from backend.security.identity import RequestIdentity
from backend.security.workspace_rbac import (
    WorkspaceAccess,
    WorkspacePermission,
    get_workspace_access,
    require_permission,
)

MAX_CONTENT_LENGTH = 20_000
MAX_HISTORY_TURNS = 20
MAX_HISTORY_CHARACTERS = 32_000
_CONTEXT_KEYS = frozenset({"project_id", "workflow_id", "run_id", "source_id", "surface"})
_SECRET_RE = re.compile(
    r"(?i)(?:bearer\s+[a-z0-9._~+/-]{8,}|(?:api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,;]{6,}|sk-[a-z0-9_-]{12,}|akia[0-9a-z]{12,})"
)


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return _SECRET_RE.sub("[REDACTED]", value)
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact(item) for key, item in value.items()}
    return value


def _safe_text(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field} must not be empty")
    if len(normalized) > MAX_CONTENT_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field} exceeds 20000 characters"
        )
    if _SECRET_RE.search(normalized):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "unsafe secret content is not persisted"
        )
    return normalized


async def validate_context_binding(
    db: AsyncSession, workspace_id: str, context: dict[str, Any] | None
) -> dict[str, Any]:
    """Return an immutable, workspace-owned context snapshot or reject it."""

    raw = context or {}
    if not isinstance(raw, dict) or set(raw) - _CONTEXT_KEYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid agent context")
    binding: dict[str, Any] = {}
    for key in ("project_id", "workflow_id", "run_id", "source_id"):
        value = raw.get(key)
        if value is not None:
            if not isinstance(value, str) or not value.strip() or len(value) > 255:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"invalid {key}")
            binding[key] = value.strip()
    surface = raw.get("surface")
    if surface is not None:
        if not isinstance(surface, str) or len(surface.strip()) > 255 or _SECRET_RE.search(surface):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid surface")
        binding["surface"] = surface.strip()

    project: Project | None = None
    if project_id := binding.get("project_id"):
        project = await db.scalar(
            select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
        )
        if project is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "project does not belong to Workspace"
            )
    workflow: Workflow | None = None
    if workflow_id := binding.get("workflow_id"):
        workflow = await db.scalar(
            select(Workflow)
            .join(Project)
            .where(Workflow.id == workflow_id, Project.workspace_id == workspace_id)
        )
        if workflow is None or (project is not None and workflow.project_id != project.id):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "workflow does not belong to context Workspace",
            )
    if run_id := binding.get("run_id"):
        run = await db.get(WorkflowRun, run_id)
        if run is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "workflow run not found")
        run_workflow = await db.scalar(
            select(Workflow)
            .join(Project)
            .where(Workflow.id == run.workflow_id, Project.workspace_id == workspace_id)
        )
        if run_workflow is None or (workflow is not None and run_workflow.id != workflow.id):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "workflow run does not belong to context Workspace",
            )
    if source_id := binding.get("source_id"):
        source = await db.scalar(
            select(Source).where(Source.id == source_id, Source.workspace_id == workspace_id)
        )
        if source is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "source does not belong to Workspace"
            )
    return binding


async def get_readable_conversation(
    db: AsyncSession, conversation_id: str, identity: RequestIdentity
) -> tuple[AgentConversation, WorkspaceAccess]:
    conversation = await db.get(AgentConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent conversation not found")
    access = await get_workspace_access(db, conversation.workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    return conversation, access


async def create_conversation(
    db: AsyncSession,
    *,
    workspace_id: str,
    identity: RequestIdentity,
    title: str | None,
    context: dict[str, Any] | None,
) -> AgentConversation:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    if title is not None:
        title = _safe_text(title, field="title")
        if len(title) > 255:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "title exceeds 255 characters"
            )
    conversation = AgentConversation(
        workspace_id=workspace_id,
        title=title,
        created_by_user_id=access.user_id,
        context_binding=await validate_context_binding(db, workspace_id, context),
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def list_conversations(
    db: AsyncSession, *, workspace_id: str, identity: RequestIdentity, limit: int
) -> list[AgentConversation]:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    return list(
        (
            await db.scalars(
                select(AgentConversation)
                .where(AgentConversation.workspace_id == workspace_id)
                .order_by(AgentConversation.updated_at.desc())
                .limit(limit)
            )
        ).all()
    )


async def list_turns(
    db: AsyncSession, conversation: AgentConversation, *, after_sequence: int, limit: int
) -> list[AgentConversationTurn]:
    return list(
        (
            await db.scalars(
                select(AgentConversationTurn)
                .where(AgentConversationTurn.conversation_id == conversation.id)
                .where(AgentConversationTurn.sequence > after_sequence)
                .order_by(AgentConversationTurn.sequence)
                .limit(limit)
            )
        ).all()
    )


async def begin_turn(
    db: AsyncSession,
    *,
    conversation: AgentConversation,
    request_id: str,
    content: str,
    context: dict[str, Any] | None,
) -> tuple[AgentConversationTurn, bool]:
    if conversation.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent conversation is closed")
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 64:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid request_id")
    existing = await db.scalar(
        select(AgentConversationTurn).where(
            AgentConversationTurn.conversation_id == conversation.id,
            AgentConversationTurn.request_id == request_id.strip(),
        )
    )
    if existing is not None:
        if existing.status == "running":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Agent conversation request is already running"
            )
        return existing, False
    content = _safe_text(content, field="content")
    binding = await validate_context_binding(db, conversation.workspace_id, context)
    sequence = (
        await db.scalar(
            select(func.coalesce(func.max(AgentConversationTurn.sequence), 0)).where(
                AgentConversationTurn.conversation_id == conversation.id
            )
        )
    ) + 1
    turn = AgentConversationTurn(
        conversation_id=conversation.id,
        workspace_id=conversation.workspace_id,
        sequence=sequence,
        request_id=request_id.strip(),
        user_content=content,
        context_binding=binding,
        status="running",
    )
    db.add(turn)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(AgentConversationTurn).where(
                AgentConversationTurn.conversation_id == conversation.id,
                AgentConversationTurn.request_id == request_id.strip(),
            )
        )
        if existing is not None and existing.status != "running":
            return existing, False
        raise HTTPException(status.HTTP_409_CONFLICT, "duplicate Agent conversation request")
    return turn, True


async def history_messages(
    db: AsyncSession, conversation_id: str, current_turn: AgentConversationTurn
) -> list[dict[str, str]]:
    turns = list(
        (
            await db.scalars(
                select(AgentConversationTurn)
                .where(AgentConversationTurn.conversation_id == conversation_id)
                .where(AgentConversationTurn.status.in_(("completed", "proposal")))
                .where(AgentConversationTurn.sequence < current_turn.sequence)
                .order_by(AgentConversationTurn.sequence.desc())
                .limit(MAX_HISTORY_TURNS - 1)
            )
        ).all()
    )
    turns.reverse()
    messages: list[dict[str, str]] = []
    for turn in turns:
        response = turn.response or {}
        assistant = response.get("content")
        if not isinstance(assistant, str):
            assistant = (response.get("proposal") or {}).get("summary")
        if isinstance(assistant, str):
            messages.extend(
                (
                    {"role": "user", "content": turn.user_content},
                    {"role": "assistant", "content": assistant},
                )
            )
    messages.extend(({"role": "user", "content": current_turn.user_content},))
    while (
        sum(len(item["content"]) for item in messages) > MAX_HISTORY_CHARACTERS
        and len(messages) > 1
    ):
        messages = messages[2:]
    return messages


async def complete_turn(
    db: AsyncSession,
    turn: AgentConversationTurn,
    response: dict[str, Any],
    trace: Iterable[dict[str, Any]],
) -> AgentConversationTurn:
    safe_response = _redact(response)
    response_type = safe_response.get("type") if isinstance(safe_response, dict) else None
    turn.response = safe_response
    turn.tool_trace = list(trace)
    turn.status = "proposal" if response_type == "proposal" else "completed"
    conversation = await db.get(AgentConversation, turn.conversation_id)
    if conversation is not None:
        conversation.revision += 1
    await db.flush()
    return turn


async def fail_turn(
    db: AsyncSession, turn: AgentConversationTurn, error_code: str
) -> AgentConversationTurn:
    turn.status = "failed"
    turn.error_code = error_code
    turn.error_message = "The model request failed. Please retry."
    await db.flush()
    return turn


async def close_conversation(
    db: AsyncSession, conversation: AgentConversation, access: WorkspaceAccess
) -> AgentConversation:
    if conversation.created_by_user_id != access.user_id and access.role.value != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the conversation owner may close it")
    if conversation.status == "active":
        conversation.status = "closed"
        conversation.revision += 1
        await db.flush()
    return conversation
