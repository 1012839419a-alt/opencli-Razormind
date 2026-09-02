from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.api.v1.chat import ApiResponse, ChatReply, Proposal
from backend.llm.base import LlmAdapterError
from backend.models import (
    AgentConversationTurn,
    Project,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from backend.security.identity import RequestIdentity
from backend.services import agent_conversation_service as service


async def _identity_and_workspace(db_session, subject: str = "agent@example.test"):
    user = User(subject=subject)
    workspace = Workspace(name="Workspace", slug=subject.split("@")[0])
    db_session.add_all([user, workspace])
    await db_session.flush()
    db_session.add(
        WorkspaceMembership(
            user_id=user.id,
            workspace_id=workspace.id,
            role=WorkspaceRole.OPERATOR,
        )
    )
    await db_session.commit()
    return RequestIdentity(subject=subject), workspace, user


@pytest.mark.asyncio
async def test_bounded_history_drops_old_pairs_but_keeps_current_message():
    turns = [
        SimpleNamespace(
            user_content="u" * 2_000,
            response={"type": "message", "content": "a" * 2_000},
        )
        for _ in range(20)
    ]

    messages = service.bounded_history(turns, "current" * 3_000)

    assert messages[-1] == {"role": "user", "content": "current" * 3_000}
    assert sum(len(message["content"]) for message in messages) <= service.MAX_HISTORY_CHARS
    assert len(messages) % 2 == 1


@pytest.mark.asyncio
async def test_context_binding_rejects_cross_workspace_project(db_session):
    identity, workspace, _ = await _identity_and_workspace(db_session, "owner@example.test")
    other_identity, other_workspace, other_user = await _identity_and_workspace(
        db_session, "other@example.test"
    )
    project = Project(
        workspace_id=other_workspace.id,
        name="Other Project",
        slug="other-project",
        created_by_user_id=other_user.id,
    )
    db_session.add(project)
    await db_session.commit()

    with pytest.raises(service.AgentConversationError):
        await service.validate_context_binding(
            db_session, workspace.id, {"project_id": project.id}
        )


@pytest.mark.asyncio
async def test_unsafe_content_is_rejected_before_persistence(db_session):
    identity, workspace, _ = await _identity_and_workspace(db_session)
    conversation = await service.create_conversation(
        db_session,
        identity,
        workspace_id=workspace.id,
        title=None,
        context=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.send_message(
            db_session,
            identity,
            conversation.id,
            request_id="unsafe-1",
            content="please use api_key=do-not-store",
            context=None,
            chat_runner=lambda *args, **kwargs: None,
        )
    assert exc_info.value.status_code == 400
    assert await db_session.scalar(
        select(AgentConversationTurn).where(
            AgentConversationTurn.conversation_id == conversation.id
        )
    ) is None


@pytest.mark.asyncio
async def test_conversation_metadata_rejects_credential_like_values(db_session):
    identity, workspace, _ = await _identity_and_workspace(db_session, "metadata@example.test")

    with pytest.raises(HTTPException) as title_error:
        await service.create_conversation(
            db_session,
            identity,
            workspace_id=workspace.id,
            title="token=do-not-store",
            context=None,
        )
    assert title_error.value.status_code == 409

    with pytest.raises(HTTPException) as context_error:
        await service.create_conversation(
            db_session,
            identity,
            workspace_id=workspace.id,
            title="safe title",
            context={"surface": "Authorization: Bearer do-not-store"},
        )
    assert context_error.value.status_code == 409


@pytest.mark.asyncio
async def test_failed_model_call_is_persisted_and_duplicate_is_idempotent(db_session):
    identity, workspace, _ = await _identity_and_workspace(db_session)
    conversation = await service.create_conversation(
        db_session,
        identity,
        workspace_id=workspace.id,
        title=None,
        context=None,
    )
    calls = 0

    async def failing_runner(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise LlmAdapterError("provider failed", retryable=True)

    with pytest.raises(HTTPException) as exc_info:
        await service.send_message(
            db_session,
            identity,
            conversation.id,
            request_id="retry-1",
            content="hello",
            context=None,
            chat_runner=failing_runner,
        )
    assert exc_info.value.status_code == 502
    turn = await db_session.scalar(
        select(AgentConversationTurn).where(
            AgentConversationTurn.conversation_id == conversation.id,
            AgentConversationTurn.request_id == "retry-1",
        )
    )
    assert turn is not None
    assert turn.status == "failed"
    assert turn.error_code == "model_unavailable"
    with pytest.raises(HTTPException):
        await service.send_message(
            db_session,
            identity,
            conversation.id,
            request_id="retry-1",
            content="hello",
            context=None,
            chat_runner=failing_runner,
        )
    assert calls == 1


@pytest.mark.asyncio
async def test_proposal_response_is_stored_without_execution(db_session, monkeypatch):
    identity, workspace, _ = await _identity_and_workspace(db_session)
    conversation = await service.create_conversation(
        db_session,
        identity,
        workspace_id=workspace.id,
        title=None,
        context=None,
    )
    executed = False

    async def runner(*args, **kwargs):
        return ApiResponse.ok(
            ChatReply(
                type="proposal",
                proposal=Proposal(
                    tool="update_provider",
                    args={"provider_id": "opaque"},
                    summary="Change provider",
                    diff="provider enabled",
                    workspace_id=workspace.id,
                    work_item_id="work-item",
                    proposal_version="version",
                ),
            )
        )

    async def forbidden_execute(*args, **kwargs):
        nonlocal executed
        executed = True
        raise AssertionError("session sends must not execute proposals")

    monkeypatch.setattr(service.agent_control_service, "execute_confirmed", forbidden_execute)
    _, turn = await service.send_message(
        db_session,
        identity,
        conversation.id,
        request_id="proposal-1",
        content="propose it",
        context=None,
        chat_runner=runner,
    )

    assert turn.status == "proposal"
    assert turn.response["type"] == "proposal"
    assert executed is False


@pytest.mark.asyncio
async def test_proposal_must_be_bound_to_conversation_workspace(db_session):
    identity, workspace, _ = await _identity_and_workspace(
        db_session, "proposal-bound@example.test"
    )
    _, other_workspace, _ = await _identity_and_workspace(
        db_session, "proposal-other@example.test"
    )
    conversation = await service.create_conversation(
        db_session,
        identity,
        workspace_id=workspace.id,
        title=None,
        context=None,
    )

    async def runner(*args, **kwargs):
        return ApiResponse.ok(
            ChatReply(
                type="proposal",
                proposal=Proposal(
                    tool="update_provider",
                    args={"provider_id": "opaque"},
                    summary="Change provider",
                    diff="provider enabled",
                    workspace_id=other_workspace.id,
                    work_item_id="work-item",
                    proposal_version="version",
                ),
            )
        )

    with pytest.raises(HTTPException) as exc_info:
        await service.send_message(
            db_session,
            identity,
            conversation.id,
            request_id="proposal-wrong-workspace",
            content="propose it",
            context=None,
            chat_runner=runner,
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_close_conversation_uses_row_lock_before_turn_insertion(db_session):
    identity, workspace, _ = await _identity_and_workspace(db_session, "close-lock@example.test")
    conversation = await service.create_conversation(
        db_session,
        identity,
        workspace_id=workspace.id,
        title=None,
        context=None,
    )
    captured = {}

    async def runner(model_db, body, actor, **kwargs):
        captured["workspace_id"] = body.workspace_id
        return ApiResponse.ok(ChatReply(type="message", content="done"))

    await service.send_message(
        db_session,
        identity,
        conversation.id,
        request_id="close-lock-1",
        content="hello",
        context=None,
        chat_runner=runner,
    )

    closed = await service.close_conversation(db_session, identity, conversation.id)

    assert captured["workspace_id"] == workspace.id
    assert closed.status == "closed"
