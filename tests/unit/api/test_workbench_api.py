from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.v1.workbench import router
from backend.database import get_db
from backend.models.identity import User, Workspace, WorkspaceMembership, WorkspaceRole
from backend.models.workbench import WorkbenchRepository, WorkbenchThread, WorkbenchTurn
from backend.security.identity import RequestIdentity, get_request_identity
from backend.services.workbench_service import append_turn_event


async def _client(db_session, identity: RequestIdentity) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def override_db():
        yield db_session

    async def override_identity():
        return identity

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_request_identity] = override_identity
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed(db_session):
    user = User(subject="workbench-operator")
    workspace = Workspace(name="Workbench", slug="workbench-api")
    db_session.add_all((user, workspace))
    await db_session.flush()
    db_session.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=WorkspaceRole.OPERATOR,
        )
    )
    repository = WorkbenchRepository(
        workspace_id=workspace.id,
        name="admin-repo",
        repository_path="/controller/private/repo",
        base_ref="refs/heads/main",
        worktree_root="/controller/private/worktrees",
        execution_node_url="http://edge-1:19823",
        shared_filesystem_id="workspace-volume-1",
    )
    db_session.add(repository)
    await db_session.flush()
    thread = WorkbenchThread(
        workspace_id=workspace.id,
        repository_id=repository.id,
        created_by_user_id=user.id,
        title="Operator request",
    )
    db_session.add(thread)
    await db_session.flush()
    turn = WorkbenchTurn(
        thread_id=thread.id,
        workspace_id=workspace.id,
        sequence=1,
        request_id="request-1",
        requirement="Fix parser",
        operations_agent_id="runtime-1",
        published_version=2,
        profile_version=3,
        runtime_type="pi",
        workflow="coding",
        base_sha="b" * 40,
        worktree_path="/controller/private/worktrees/turn-1",
        status="proposed",
    )
    db_session.add(turn)
    await db_session.flush()
    await append_turn_event(
        db_session, turn=turn, event_type="started", payload={"task_id": "task-1"}
    )
    await append_turn_event(
        db_session, turn=turn, event_type="text", payload={"text": "examining files"}
    )
    await db_session.commit()
    return workspace, repository, thread, turn


async def test_repository_catalog_exposes_only_server_safe_fields(db_session):
    workspace, repository, _, _ = await _seed(db_session)
    client = await _client(db_session, RequestIdentity(subject="workbench-operator"))

    async with client:
        response = await client.get(f"/workspaces/{workspace.id}/workbench/repositories")

    assert response.status_code == 200
    catalog = response.json()["data"]
    assert catalog == [{"id": repository.id, "name": "admin-repo", "defaultRef": "refs/heads/main"}]
    assert "repository_path" not in response.text
    assert "worktree_root" not in response.text


async def test_event_replay_is_ordered_and_last_event_id_resumes(db_session):
    workspace, _, thread, turn = await _seed(db_session)
    client = await _client(db_session, RequestIdentity(subject="workbench-operator"))
    base = f"/workspaces/{workspace.id}/workbench/threads/{thread.id}/turns/{turn.id}/events"

    async with client:
        replay = await client.get(base, params={"afterSequence": 0})
        stream = await client.get(
            f"{base}/stream",
            params={"afterSequence": 0},
            headers={"Last-Event-ID": "1"},
        )

    assert replay.status_code == 200
    assert [event["sequence"] for event in replay.json()["data"]] == [1, 2]
    assert stream.status_code == 200
    assert "id: 2\nevent: workbench_event" in stream.text
    assert "id: 1\nevent: workbench_event" not in stream.text
    assert 'event: turn_state\ndata: {"turnId"' in stream.text
