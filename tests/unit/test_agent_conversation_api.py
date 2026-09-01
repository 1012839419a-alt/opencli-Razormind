import pytest
from fastapi import HTTPException

from backend.api.v1.agent_conversations import (
    close_session,
    create_session,
    get_session,
)
from backend.models import AgentConversationTurn
from backend.schemas.agent_conversation import AgentConversationCreate
from backend.security.identity import RequestIdentity
from backend.services import agent_conversation_service as service


async def _identity_and_workspace(db_session, subject: str):
    from backend.models import User, Workspace, WorkspaceMembership, WorkspaceRole

    user = User(subject=subject)
    workspace = Workspace(name=subject, slug=subject.split("@")[0])
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
    return RequestIdentity(subject=subject), workspace


@pytest.mark.asyncio
async def test_create_and_detail_route_returns_replayable_turns(db_session):
    identity, workspace = await _identity_and_workspace(db_session, "api@example.test")
    created = await create_session(
        AgentConversationCreate(workspace_id=workspace.id, title="Dock"),
        identity=identity,
        db=db_session,
    )
    conversation = created.data
    row = AgentConversationTurn(
        conversation_id=conversation.id,
        workspace_id=workspace.id,
        sequence=1,
        request_id="request-1",
        user_content="hello",
        response={"type": "message", "content": "hi"},
        context_binding={},
        tool_trace=[],
        status="completed",
    )
    db_session.add(row)
    await db_session.commit()

    detail = await get_session(
        conversation.id,
        after_sequence=0,
        limit=50,
        identity=identity,
        db=db_session,
    )
    assert [turn.sequence for turn in detail.data.turns] == [1]

    replay = await get_session(
        conversation.id,
        after_sequence=1,
        limit=50,
        identity=identity,
        db=db_session,
    )
    assert replay.data.turns == []


@pytest.mark.asyncio
async def test_cross_workspace_detail_and_close_are_denied(db_session):
    owner, workspace = await _identity_and_workspace(db_session, "owner-api@example.test")
    outsider, _ = await _identity_and_workspace(db_session, "outsider-api@example.test")
    created = await service.create_conversation(
        db_session,
        owner,
        workspace_id=workspace.id,
        title=None,
        context=None,
    )

    with pytest.raises(HTTPException) as detail_error:
        await get_session(
            created.id,
            identity=outsider,
            db=db_session,
        )
    assert detail_error.value.status_code == 403

    with pytest.raises(HTTPException) as close_error:
        await close_session(created.id, identity=outsider, db=db_session)
    assert close_error.value.status_code == 403
