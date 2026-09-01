import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.models.agent_conversation import AgentConversationTurn
from backend.models.identity import User, Workspace, WorkspaceMembership, WorkspaceRole
from backend.services import agent_conversation_service as service


async def _member(db_session, subject: str = "agent-user"):
    user = User(subject=subject)
    workspace = Workspace(name="Agent Workspace", slug=f"agent-{subject}")
    db_session.add_all((user, workspace))
    await db_session.flush()
    db_session.add(
        WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.ADMIN)
    )
    await db_session.commit()
    from backend.security.identity import RequestIdentity

    return user, workspace, RequestIdentity(subject=subject)


@pytest.mark.asyncio
async def test_turn_idempotency_and_redacted_response(db_session):
    _, workspace, identity = await _member(db_session)
    conversation = await service.create_conversation(
        db_session, workspace_id=workspace.id, identity=identity, title="A session", context={}
    )
    turn, created = await service.begin_turn(
        db_session,
        conversation=conversation,
        request_id="request-1",
        content="hello",
        context={"surface": "agents"},
    )
    assert created is True
    await service.complete_turn(
        db_session,
        turn,
        {"type": "message", "content": "Bearer abcdefghijklmnop"},
        [],
    )
    same, created = await service.begin_turn(
        db_session,
        conversation=conversation,
        request_id="request-1",
        content="ignored",
        context={},
    )
    assert created is False
    assert same.id == turn.id
    assert same.status == "completed"
    assert same.response["content"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_secret_input_and_cross_workspace_source_are_rejected_without_turn(db_session):
    _, workspace, identity = await _member(db_session)
    conversation = await service.create_conversation(
        db_session, workspace_id=workspace.id, identity=identity, title=None, context={}
    )
    with pytest.raises(HTTPException, match="unsafe secret"):
        await service.begin_turn(
            db_session,
            conversation=conversation,
            request_id="unsafe",
            content="api_key=super-secret-value",
            context={},
        )
    with pytest.raises(HTTPException, match="source does not belong"):
        await service.begin_turn(
            db_session,
            conversation=conversation,
            request_id="foreign-source",
            content="safe",
            context={"source_id": "not-in-this-workspace"},
        )
    assert await db_session.scalar(select(AgentConversationTurn)) is None


@pytest.mark.asyncio
async def test_history_is_bounded_and_keeps_current_turn(db_session):
    _, workspace, identity = await _member(db_session)
    conversation = await service.create_conversation(
        db_session, workspace_id=workspace.id, identity=identity, title=None, context={}
    )
    for sequence in range(1, 24):
        db_session.add(
            AgentConversationTurn(
                conversation_id=conversation.id,
                workspace_id=workspace.id,
                sequence=sequence,
                request_id=f"old-{sequence}",
                user_content="u" * 2_000,
                response={"type": "message", "content": "a" * 2_000},
                context_binding={},
                status="completed",
            )
        )
    current = AgentConversationTurn(
        conversation_id=conversation.id,
        workspace_id=workspace.id,
        sequence=24,
        request_id="current",
        user_content="current",
        context_binding={},
        status="running",
    )
    db_session.add(current)
    await db_session.commit()
    messages = await service.history_messages(db_session, conversation.id, current)
    assert messages[-1] == {"role": "user", "content": "current"}
    assert len(messages) <= service.MAX_HISTORY_TURNS
    assert sum(len(item["content"]) for item in messages) <= service.MAX_HISTORY_CHARACTERS
