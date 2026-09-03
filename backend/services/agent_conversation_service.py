"""Persistence and execution boundary for Global Agent conversations.

Conversation rows contain bounded, redacted continuity data only. Product state and
proposal execution remain owned by their existing services.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.v1 import chat
from backend.control.agent_control import agent_control_service
from backend.llm.base import LlmAdapterError
from backend.llm.resolver import ResolverError
from backend.models.agent_conversation import (
    AgentConversation,
    AgentConversationStatus,
    AgentConversationTurn,
    AgentConversationTurnStatus,
)
from backend.models.source_binding import Source, SourceBinding
from backend.models.workflow import Project, Workflow
from backend.models.workflow_run import WorkflowRun
from backend.security.identity import RequestIdentity
from backend.security.workspace_rbac import (
    WorkspacePermission,
    get_workspace_access,
    require_permission,
)

MAX_USER_CONTENT = 20_000
MAX_HISTORY_TURNS = 20
MAX_HISTORY_CHARS = 32_000
MAX_ERROR_MESSAGE = 4_000
_ALLOWED_CONTEXT_KEYS = frozenset({"project_id", "workflow_id", "run_id", "source_id", "surface"})
_SECRET_PATTERN = re.compile(
    r"(?ix)(?:"
    r"(?:api[_ -]?key|access[_ -]?token|authorization|password|secret|credential|"
    r"connection[_ -]?string|token)\s*(?:[:=]|is)\s*(?:bearer\s+)?[^\s,;]+"
    r"|bearer\s+[^\s,;]+"
    r")"
)
_URL_PATTERN = re.compile(r"https?://[^\s,;]+", re.IGNORECASE)


class AgentConversationError(ValueError):
    """Stable client-facing validation failure before a turn is written."""


async def resolve_workspace(
    db: AsyncSession, identity: RequestIdentity, workspace_id: str | None
) -> str:
    """Use Agent Control's existing Workspace resolution and auth boundary."""

    try:
        return await agent_control_service.resolve_workspace_id(db, identity, workspace_id)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_400_BAD_REQUEST:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "workspace_id is required when the actor belongs to multiple workspaces",
            ) from exc
        raise


async def validate_context_binding(
    db: AsyncSession,
    workspace_id: str,
    context: dict[str, Any] | None,
) -> dict[str, str]:
    """Validate object ownership and return an immutable, bounded snapshot."""

    context = context or {}
    if not isinstance(context, dict):
        raise AgentConversationError("context must be an object")
    unknown = set(context) - _ALLOWED_CONTEXT_KEYS
    if unknown:
        raise AgentConversationError("context contains unsupported fields")

    normalized: dict[str, str] = {}
    for key in _ALLOWED_CONTEXT_KEYS:
        value = context.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or len(value) > 255:
            raise AgentConversationError(f"context.{key} must be a bounded non-empty string")
        normalized_value = value.strip()
        _reject_unsafe_content(normalized_value)
        normalized[key] = normalized_value
    project_id = normalized.get("project_id")
    workflow_id = normalized.get("workflow_id")
    run_id = normalized.get("run_id")
    source_id = normalized.get("source_id")

    project: Project | None = None
    if project_id:
        project = await db.scalar(
            select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
        )
        if project is None:
            raise AgentConversationError("project is not owned by the Workspace")

    workflow: Workflow | None = None
    if workflow_id:
        workflow = await db.scalar(
            select(Workflow)
            .join(Project, Project.id == Workflow.project_id)
            .where(Workflow.id == workflow_id, Project.workspace_id == workspace_id)
        )
        if workflow is None:
            raise AgentConversationError("workflow is not owned by the Workspace")
        if project_id and workflow.project_id != project_id:
            raise AgentConversationError("workflow does not belong to project")

    if run_id:
        run = await db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        if run is None:
            raise AgentConversationError("run is not available in the Workspace")
        if workflow_id and run.workflow_id != workflow_id:
            raise AgentConversationError("run does not belong to workflow")
        if workflow is None:
            workflow = await db.scalar(
                select(Workflow)
                .join(Project, Project.id == Workflow.project_id)
                .where(Workflow.id == run.workflow_id, Project.workspace_id == workspace_id)
            )
            if workflow is None:
                raise AgentConversationError("run is not owned by the Workspace")
        if project is None:
            project = await db.get(Project, workflow.project_id)
        if project is None or project.workspace_id != workspace_id:
            raise AgentConversationError("run is not owned by the Workspace")

    if source_id:
        source = await db.scalar(
            select(Source).where(Source.id == source_id, Source.workspace_id == workspace_id)
        )
        if source is None:
            # A SourceBinding is also a valid proof of Workspace ownership when
            # callers identify the project-scoped binding rather than the source.
            source = await db.scalar(
                select(Source)
                .join(SourceBinding, SourceBinding.source_id == Source.id)
                .join(Project, Project.id == SourceBinding.project_id)
                .where(Source.id == source_id, Project.workspace_id == workspace_id)
            )
        if source is None:
            raise AgentConversationError("source is not owned by the Workspace")

    return dict(normalized)


def _reject_unsafe_content(content: str) -> None:
    if not content.strip():
        raise AgentConversationError("content must not be empty")
    if len(content) > MAX_USER_CONTENT:
        raise AgentConversationError("content exceeds the 20000 character limit")
    if _SECRET_PATTERN.search(content):
        raise AgentConversationError("content contains a credential-like value")


def _redact_error(value: str) -> str:
    value = _SECRET_PATTERN.sub("[REDACTED]", value)
    return _URL_PATTERN.sub("[REDACTED_URL]", value)[:MAX_ERROR_MESSAGE]


_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(?:api[_ -]?key|access[_ -]?token|authorization|bearer|password|"
    r"secret|credential|connection|token|cookie|header|endpoint|profile|html|url)"
)


def _redact_json(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            name: "[REDACTED]"
            if _SENSITIVE_KEY_PATTERN.search(name)
            else _redact_json(item, key=name)
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(item, key=key) for item in value]
    if isinstance(value, str):
        return _redact_error(value)
    return value


def _assistant_history(response: dict[str, Any] | None) -> str:
    if not response:
        return ""
    if response.get("type") == "message":
        content = response.get("content")
        return content if isinstance(content, str) else ""
    proposal = response.get("proposal")
    if isinstance(proposal, dict):
        summary = proposal.get("summary")
        return summary if isinstance(summary, str) else ""
    return ""


def bounded_history(
    turns: list[AgentConversationTurn], current_content: str
) -> list[dict[str, str]]:
    """Return complete user/assistant pairs inside the model context budget."""

    pairs: list[tuple[str, str]] = []
    for turn in turns[-MAX_HISTORY_TURNS:]:
        assistant = _assistant_history(turn.response)
        if assistant:
            pairs.append((turn.user_content, assistant))

    while (
        pairs
        and sum(len(user) + len(assistant) for user, assistant in pairs) + len(current_content)
        > MAX_HISTORY_CHARS
    ):
        pairs.pop(0)

    messages: list[dict[str, str]] = []
    for user, assistant in pairs:
        messages.extend(
            ({"role": "user", "content": user}, {"role": "assistant", "content": assistant})
        )
    messages.append({"role": "user", "content": current_content})
    return messages


def _safe_response(reply: chat.ChatReply) -> dict[str, Any]:
    """Persist only the public reply shape, never an SDK/model message."""

    response: dict[str, Any] = {"type": reply.type}
    if reply.content is not None:
        response["content"] = _redact_error(reply.content[:MAX_USER_CONTENT])
    if reply.proposal is not None:
        response["proposal"] = _redact_json(reply.proposal.model_dump(exclude_none=True))
    return response


async def create_conversation(
    db: AsyncSession,
    identity: RequestIdentity,
    *,
    workspace_id: str | None,
    title: str | None,
    context: dict[str, Any] | None,
) -> AgentConversation:
    workspace_id = await resolve_workspace(db, identity, workspace_id)
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    title_value = title.strip() if title else None
    try:
        binding = await validate_context_binding(db, workspace_id, context)
        if title_value:
            _reject_unsafe_content(title_value)
    except AgentConversationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    conversation = AgentConversation(
        workspace_id=workspace_id,
        title=title_value,
        created_by_user_id=access.user_id,
        context_binding=binding,
        status=AgentConversationStatus.ACTIVE.value,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def list_conversations(
    db: AsyncSession,
    identity: RequestIdentity,
    *,
    workspace_id: str | None,
    limit: int,
) -> list[AgentConversation]:
    workspace_id = await resolve_workspace(db, identity, workspace_id)
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    rows = await db.scalars(
        select(AgentConversation)
        .where(AgentConversation.workspace_id == workspace_id)
        .order_by(AgentConversation.updated_at.desc())
        .limit(limit)
    )
    return list(rows)


async def get_conversation(
    db: AsyncSession,
    identity: RequestIdentity,
    conversation_id: str,
    *,
    after_sequence: int = 0,
    limit: int = 50,
    for_update: bool = False,
) -> tuple[AgentConversation, list[AgentConversationTurn]]:
    statement = select(AgentConversation).where(AgentConversation.id == conversation_id)
    if for_update:
        statement = statement.with_for_update()
    conversation = await db.scalar(statement)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent conversation not found")
    access = await get_workspace_access(db, conversation.workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    turns = await db.scalars(
        select(AgentConversationTurn)
        .where(
            AgentConversationTurn.conversation_id == conversation_id,
            AgentConversationTurn.sequence > after_sequence,
        )
        .order_by(AgentConversationTurn.sequence.asc())
        .limit(limit)
    )
    return conversation, list(turns)


async def close_conversation(
    db: AsyncSession, identity: RequestIdentity, conversation_id: str
) -> AgentConversation:
    conversation, _ = await get_conversation(
        db, identity, conversation_id, limit=1, for_update=True
    )
    if conversation.status != AgentConversationStatus.CLOSED.value:
        conversation.status = AgentConversationStatus.CLOSED.value
        conversation.revision += 1
        await db.commit()
        await db.refresh(conversation)
    return conversation


async def _insert_running_turn(
    db: AsyncSession,
    conversation: AgentConversation,
    request_id: str,
    content: str,
    binding: dict[str, str],
) -> tuple[AgentConversationTurn | None, AgentConversationTurn | None]:
    """Insert once; return (new_turn, existing_turn) under duplicate races."""

    for _ in range(2):
        sequence = (
            await db.scalar(
                select(func.max(AgentConversationTurn.sequence)).where(
                    AgentConversationTurn.conversation_id == conversation.id
                )
            )
            or 0
        ) + 1
        turn = AgentConversationTurn(
            conversation_id=conversation.id,
            workspace_id=conversation.workspace_id,
            sequence=sequence,
            request_id=request_id,
            user_content=content,
            context_binding=binding,
            tool_trace=[],
            status=AgentConversationTurnStatus.RUNNING.value,
        )
        db.add(turn)
        try:
            await db.commit()
            await db.refresh(turn)
            return turn, None
        except IntegrityError:
            await db.rollback()
            existing = await db.scalar(
                select(AgentConversationTurn).where(
                    AgentConversationTurn.conversation_id == conversation.id,
                    AgentConversationTurn.request_id == request_id,
                )
            )
            if existing is not None:
                return None, existing
    raise HTTPException(status.HTTP_409_CONFLICT, "Could not allocate conversation turn")


async def _model_session(db: AsyncSession) -> AsyncSession:
    bind = db.bind
    if bind is None:
        raise RuntimeError("conversation database session has no bind")
    return async_sessionmaker(bind=bind, expire_on_commit=False)()


async def send_message(
    db: AsyncSession,
    identity: RequestIdentity,
    conversation_id: str,
    *,
    request_id: str,
    content: str,
    context: dict[str, Any] | None,
    chat_runner: Callable[..., Any] | None = None,
) -> tuple[AgentConversation, AgentConversationTurn]:
    if not request_id.strip() or len(request_id) > 64:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "request_id must be 1..64 characters"
        )
    try:
        _reject_unsafe_content(content)
    except AgentConversationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    conversation = await db.scalar(
        select(AgentConversation)
        .where(AgentConversation.id == conversation_id)
        .with_for_update()
    )
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent conversation not found")
    access = await get_workspace_access(db, conversation.workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    existing = await db.scalar(
        select(AgentConversationTurn).where(
            AgentConversationTurn.conversation_id == conversation_id,
            AgentConversationTurn.request_id == request_id,
        )
    )
    if existing is not None:
        if existing.status == AgentConversationTurnStatus.RUNNING.value:
            raise HTTPException(status.HTTP_409_CONFLICT, "conversation turn is already running")
        if existing.status == AgentConversationTurnStatus.FAILED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, "conversation turn previously failed")
        return conversation, existing
    if conversation.status != AgentConversationStatus.ACTIVE.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent conversation is closed")

    try:
        binding = await validate_context_binding(
            db,
            conversation.workspace_id,
            context if context is not None else conversation.context_binding,
        )
    except AgentConversationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    history_rows = list(
        await db.scalars(
            select(AgentConversationTurn)
            .where(
                AgentConversationTurn.conversation_id == conversation_id,
                AgentConversationTurn.status.in_(
                    (
                        AgentConversationTurnStatus.COMPLETED.value,
                        AgentConversationTurnStatus.PROPOSAL.value,
                    )
                ),
            )
            .order_by(AgentConversationTurn.sequence.desc())
            .limit(MAX_HISTORY_TURNS)
        )
    )
    history_rows.reverse()
    turn, existing = await _insert_running_turn(db, conversation, request_id, content, binding)
    if existing is not None:
        if existing.status == AgentConversationTurnStatus.RUNNING.value:
            raise HTTPException(status.HTTP_409_CONFLICT, "conversation turn is already running")
        if existing.status == AgentConversationTurnStatus.FAILED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, "conversation turn previously failed")
        return conversation, existing
    assert turn is not None

    trace: list[dict[str, Any]] = []
    body = chat.ChatRequest(
        messages=bounded_history(history_rows, content),
        workspace_id=conversation.workspace_id,
        context=binding,
    )
    model_db = await _model_session(db)
    try:
        runner = chat_runner or chat.run_chat_request
        result = await runner(model_db, body, identity, tool_trace=trace)
        reply = result.data if isinstance(result, chat.ApiResponse) else result
        if not isinstance(reply, chat.ChatReply):
            raise RuntimeError("chat runner returned an invalid reply")
        if reply.type == "proposal":
            proposal = reply.proposal
            if (
                proposal is None
                or proposal.workspace_id != conversation.workspace_id
                or not proposal.work_item_id
                or not proposal.proposal_version
            ):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Agent proposal is not bound to the conversation Workspace",
                )
        turn.response = _safe_response(reply)
        turn.tool_trace = trace
        turn.status = (
            AgentConversationTurnStatus.PROPOSAL.value
            if reply.type == "proposal"
            else AgentConversationTurnStatus.COMPLETED.value
        )
        conversation.revision += 1
        await model_db.commit()
        await db.commit()
        await db.refresh(turn)
        await db.refresh(conversation)
        return conversation, turn
    except (LlmAdapterError, ResolverError) as exc:
        await model_db.rollback()
        turn.status = AgentConversationTurnStatus.FAILED.value
        turn.error_code = (
            "model_unavailable"
            if isinstance(exc, LlmAdapterError) and exc.retryable
            else "model_error"
        )
        turn.error_message = _redact_error(str(exc))
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "模型调用失败") from exc
    except HTTPException as exc:
        await model_db.rollback()
        turn.status = AgentConversationTurnStatus.FAILED.value
        turn.error_code = "model_error"
        turn.error_message = _redact_error(str(exc.detail))
        await db.commit()
        raise
    except Exception as exc:
        await model_db.rollback()
        turn.status = AgentConversationTurnStatus.FAILED.value
        turn.error_code = "model_error"
        turn.error_message = _redact_error(str(exc))
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "模型调用失败") from exc
    finally:
        await model_db.close()
