"""Chat dock AI-provider and durable streaming coverage."""

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import backend.api.v1.chat as chat_api
from backend.api.v1.chat import _build_proposal, _run_read_tool
from backend.main import app
from backend.models.identity import User, Workspace, WorkspaceMembership, WorkspaceRole
from backend.models.operations_work_item import OperationsWorkItem, WorkItemStatus
from backend.models.provider import ModelProvider
from backend.security.identity import RequestIdentity, get_request_identity


async def _make_provider(db_session, **overrides) -> ModelProvider:
    provider = ModelProvider(
        name=overrides.get("name", "Test Provider"),
        provider_type=overrides.get("provider_type", "openai"),
        base_url=overrides.get("base_url", "https://api.openai.com/v1"),
        api_key=overrides.get("api_key", "sk-test-key"),
        default_model=overrides.get("default_model", "gpt-4o-mini"),
        enabled=overrides.get("enabled", True),
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider


async def _authorize_chat(
    db_session,
    *,
    subject: str = "chat-admin",
    role: WorkspaceRole = WorkspaceRole.ADMIN,
) -> tuple[RequestIdentity, User, Workspace]:
    identity = RequestIdentity(subject=subject)
    user = User(subject=subject)
    workspace = Workspace(name=f"Chat {subject}", slug=f"chat-{subject}")
    db_session.add_all([user, workspace])
    await db_session.flush()
    db_session.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=role,
        )
    )
    await db_session.commit()

    async def override_identity():
        return identity

    app.dependency_overrides[get_request_identity] = override_identity
    return identity, user, workspace


class _NoToolCompletions:
    async def create(self, **_kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="已完成只读检查。",
                        tool_calls=None,
                    )
                )
            ]
        )


def _no_tool_client():
    return SimpleNamespace(chat=SimpleNamespace(completions=_NoToolCompletions()))


class _FailingCompletions:
    async def create(self, **_kwargs):
        raise RuntimeError("model unavailable")


class _WriteProposalCompletions:
    def __init__(self, provider_id: str):
        self.provider_id = provider_id

    async def create(self, **_kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="",
                        tool_calls=[
                            SimpleNamespace(
                                id="call-update-provider",
                                function=SimpleNamespace(
                                    name="update_provider",
                                    arguments=json.dumps(
                                        {"provider_id": self.provider_id, "enabled": False}
                                    ),
                                ),
                            )
                        ],
                    )
                )
            ]
        )


# ── durable stream: public events survive replay without commit amplification ─
@pytest.mark.asyncio
async def test_no_tool_chat_stream_is_ordered_recoverable_and_commit_bounded(
    client,
    db_engine,
    db_session,
    monkeypatch,
):
    provider = await _make_provider(db_session)
    provider_id = provider.id
    await db_session.rollback()

    stream_sessions = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    monkeypatch.setattr(chat_api, "AsyncSessionLocal", stream_sessions)

    async def build_client(_provider):
        return _no_tool_client()

    monkeypatch.setattr(chat_api, "_build_client", build_client)

    commit_count = 0

    def count_commit(_connection):
        nonlocal commit_count
        commit_count += 1

    event.listen(db_engine.sync_engine, "commit", count_commit)
    try:
        response = await client.post(
            "/api/v1/chat/stream",
            json={
                "provider_id": provider_id,
                "messages": [{"role": "user", "content": "检查当前状态"}],
            },
        )
    finally:
        event.remove(db_engine.sync_engine, "commit", count_commit)

    assert response.status_code == 200
    streamed = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [item["sequence"] for item in streamed] == [1, 2, 3, 4, 5, 6]
    assert [item["type"] for item in streamed] == [
        "run.started",
        "phase.changed",
        "phase.changed",
        "phase.changed",
        "run.completed",
        "reply",
    ]
    assert streamed[-1]["reply"] == {
        "type": "message",
        "content": "已完成只读检查。",
        "proposal": None,
    }
    assert commit_count <= 4

    await db_session.rollback()
    run_id = response.headers["X-Agent-Run-Id"]
    replay = await client.get(f"/api/v1/chat/runs/{run_id}/events")
    assert replay.status_code == 200
    assert replay.json()["data"] == streamed

    run = await client.get(f"/api/v1/chat/runs/{run_id}")
    assert run.status_code == 200
    assert run.json()["data"]["status"] == "completed"
    assert run.json()["data"]["reply"] == streamed[-1]["reply"]


@pytest.mark.asyncio
async def test_failed_chat_stream_persists_recoverable_terminal_event(
    client,
    db_engine,
    db_session,
    monkeypatch,
):
    provider = await _make_provider(db_session)
    provider_id = provider.id
    await db_session.rollback()
    stream_sessions = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    monkeypatch.setattr(chat_api, "AsyncSessionLocal", stream_sessions)

    async def build_client(_provider):
        return SimpleNamespace(chat=SimpleNamespace(completions=_FailingCompletions()))

    monkeypatch.setattr(chat_api, "_build_client", build_client)

    response = await client.post(
        "/api/v1/chat/stream",
        json={
            "provider_id": provider_id,
            "messages": [{"role": "user", "content": "检查当前状态"}],
        },
    )

    assert response.status_code == 200
    streamed = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [item["sequence"] for item in streamed] == [1, 2, 3, 4, 5]
    assert [item["type"] for item in streamed] == [
        "run.started",
        "phase.changed",
        "phase.changed",
        "phase.changed",
        "run.failed",
    ]
    assert streamed[-1]["status"] == 502
    assert "model unavailable" in streamed[-1]["detail"]

    await db_session.rollback()
    run_id = response.headers["X-Agent-Run-Id"]
    replay = await client.get(f"/api/v1/chat/runs/{run_id}/events")
    assert replay.status_code == 200
    assert replay.json()["data"] == streamed
    run = await client.get(f"/api/v1/chat/runs/{run_id}")
    assert run.json()["data"]["status"] == "failed"
    assert "model unavailable" in run.json()["data"]["error"]


@pytest.mark.asyncio
async def test_writer_commit_failure_uses_fresh_session_for_recoverable_failure(
    client,
    db_engine,
    db_session,
    monkeypatch,
):
    provider = await _make_provider(db_session)
    provider_id = provider.id
    await db_session.rollback()
    stream_sessions = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    monkeypatch.setattr(chat_api, "AsyncSessionLocal", stream_sessions)

    async def build_client(_provider):
        return _no_tool_client()

    monkeypatch.setattr(chat_api, "_build_client", build_client)

    commit_attempts = 0

    def fail_first_writer_commit(_connection):
        nonlocal commit_attempts
        commit_attempts += 1
        if commit_attempts == 2:
            raise RuntimeError("injected writer commit failure")

    event.listen(db_engine.sync_engine, "commit", fail_first_writer_commit)
    try:
        response = await client.post(
            "/api/v1/chat/stream",
            json={
                "provider_id": provider_id,
                "messages": [{"role": "user", "content": "检查当前状态"}],
            },
        )
    finally:
        event.remove(db_engine.sync_engine, "commit", fail_first_writer_commit)

    assert response.status_code == 200
    streamed = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [item["sequence"] for item in streamed] == [1]
    assert [item["type"] for item in streamed] == ["run.failed"]
    assert streamed[0]["status"] == 500
    assert streamed[0]["recovery"]
    assert commit_attempts == 3

    await db_session.rollback()
    run_id = response.headers["X-Agent-Run-Id"]
    replay = await client.get(f"/api/v1/chat/runs/{run_id}/events")
    assert replay.status_code == 200
    assert replay.json()["data"] == streamed
    run = await client.get(f"/api/v1/chat/runs/{run_id}")
    assert run.status_code == 200
    assert run.json()["data"]["status"] == "failed"
    assert run.json()["data"]["error"]


@pytest.mark.asyncio
async def test_write_tool_stream_returns_confirmable_durable_approval(
    client,
    db_engine,
    db_session,
    monkeypatch,
):
    provider = await _make_provider(db_session, enabled=True)
    provider_id = provider.id
    identity, _, workspace = await _authorize_chat(db_session, subject="stream-proposal-admin")
    await db_session.rollback()
    stream_sessions = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    monkeypatch.setattr(chat_api, "AsyncSessionLocal", stream_sessions)

    async def optional_identity():
        return identity

    app.dependency_overrides[chat_api._optional_request_identity] = optional_identity

    async def build_client(_provider):
        return SimpleNamespace(
            chat=SimpleNamespace(completions=_WriteProposalCompletions(provider_id))
        )

    monkeypatch.setattr(chat_api, "_build_client", build_client)

    response = await client.post(
        "/api/v1/chat/stream",
        json={
            "provider_id": provider_id,
            "context": {"workspace_id": workspace.id},
            "messages": [{"role": "user", "content": "停用这个模型提供商"}],
        },
    )

    assert response.status_code == 200
    streamed = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [item["sequence"] for item in streamed] == [1, 2, 3, 4, 5, 6, 7]
    assert [item["type"] for item in streamed] == [
        "run.started",
        "phase.changed",
        "phase.changed",
        "phase.changed",
        "tool.completed",
        "approval.required",
        "reply",
    ]
    proposal = streamed[-1]["reply"]["proposal"]
    assert proposal["workspace_id"] == workspace.id
    assert proposal["work_item_id"]
    assert proposal["proposal_version"]

    await db_session.rollback()
    run_id = response.headers["X-Agent-Run-Id"]
    replay = await client.get(f"/api/v1/chat/runs/{run_id}/events")
    assert replay.status_code == 200
    assert replay.json()["data"] == streamed

    confirmation = await client.post("/api/v1/chat/confirm", json={"proposal": proposal})
    assert confirmation.status_code == 200
    assert confirmation.json()["data"]["applied"] is True
    await db_session.refresh(provider)
    assert provider.enabled is False


# ── read: list_providers ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_providers_read_tool_empty(db_session):
    result = await _run_read_tool(db_session, "list_providers", {})
    assert result == []


@pytest.mark.asyncio
async def test_list_providers_read_tool_returns_enabled_and_disabled(db_session):
    enabled = await _make_provider(db_session, name="Enabled One", enabled=True)
    disabled = await _make_provider(db_session, name="Disabled One", enabled=False)

    result = await _run_read_tool(db_session, "list_providers", {})

    assert {p["id"] for p in result} == {enabled.id, disabled.id}
    by_id = {p["id"]: p for p in result}
    assert by_id[enabled.id]["enabled"] is True
    assert by_id[disabled.id]["enabled"] is False
    assert set(by_id[enabled.id]) == {
        "id",
        "name",
        "provider_type",
        "default_model",
        "base_url",
        "enabled",
    }


# ── write: update_provider proposal ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_update_provider_proposal_default_model(db_session):
    provider = await _make_provider(db_session, default_model="gpt-4o-mini")

    proposal = await _build_proposal(
        db_session, "update_provider", {"provider_id": provider.id, "default_model": "qwen3:4b"}
    )

    assert proposal.tool == "update_provider"
    assert proposal.args == {"provider_id": provider.id, "default_model": "qwen3:4b"}
    assert "gpt-4o-mini" in proposal.diff and "qwen3:4b" in proposal.diff
    # proposing never mutates the row
    await db_session.refresh(provider)
    assert provider.default_model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_update_provider_proposal_enabled_toggle(db_session):
    provider = await _make_provider(db_session, enabled=True)

    proposal = await _build_proposal(
        db_session,
        "update_provider",
        {"provider_id": provider.id, "enabled": False},
    )

    assert proposal.args == {"provider_id": provider.id, "enabled": False}
    assert "启用" in proposal.diff or "停用" in proposal.diff


@pytest.mark.asyncio
async def test_update_provider_proposal_not_found(db_session):
    with pytest.raises(HTTPException) as exc_info:
        await _build_proposal(
            db_session,
            "update_provider",
            {"provider_id": "nonexistent-id", "enabled": True},
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_provider_proposal_no_fields(db_session):
    provider = await _make_provider(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await _build_proposal(db_session, "update_provider", {"provider_id": provider.id})
    assert exc_info.value.status_code == 400


# ── confirm: POST /api/v1/chat/confirm ───────────────────────────────────────
@pytest.mark.asyncio
async def test_confirm_update_provider(client, db_session):
    provider = await _make_provider(db_session, default_model="gpt-4o-mini", enabled=True)
    _, user, workspace = await _authorize_chat(db_session)

    response = await client.post(
        "/api/v1/chat/confirm",
        json={
            "proposal": {
                "tool": "update_provider",
                "args": {"provider_id": provider.id, "default_model": "qwen3:4b", "enabled": False},
                "summary": "配置 AI 模型提供商",
                "diff": "default_model gpt-4o-mini -> qwen3:4b",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["applied"] is True
    assert body["tool"] == "update_provider"

    await db_session.refresh(provider)
    assert provider.default_model == "qwen3:4b"
    assert provider.enabled is False
    work_item = await db_session.get(OperationsWorkItem, body["work_item_id"])
    assert work_item is not None
    assert work_item.workspace_id == workspace.id
    assert work_item.author_actor_type == "user"
    assert work_item.author_actor_id == user.id
    assert work_item.status == WorkItemStatus.RESOLVED
    assert work_item.evidence["proposal_version"] == body["proposal_version"]
    assert work_item.evidence["approval_grant"]["proposal_version"] == body["proposal_version"]


@pytest.mark.asyncio
async def test_confirm_update_provider_not_found(client, db_session):
    await _authorize_chat(db_session)
    response = await client.post(
        "/api/v1/chat/confirm",
        json={
            "proposal": {
                "tool": "update_provider",
                "args": {"provider_id": "nonexistent-id", "enabled": True},
                "summary": "配置 AI 模型提供商",
                "diff": "enabled -> true",
            }
        },
    )
    assert response.status_code == 404


# ── confirm: trigger_task dispatch failure ───────────────────────────────────
@pytest.mark.asyncio
async def test_confirm_trigger_task_reports_dispatch_failure(client, db_session, monkeypatch):
    """Dispatch blowing up after the task row is committed must surface as 502,
    not applied=True with a silently dead task."""
    from backend.models.source import DataSource

    source = DataSource(
        name="Chat Trigger Source",
        channel_type="rss",
        channel_config={"feed_url": "https://example.com/feed.xml"},
        enabled=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    await _authorize_chat(db_session)

    class _BoomExecutor:
        async def dispatch_collection(self, task_id: str, parameters: dict) -> dict:
            raise RuntimeError("broker down")

    monkeypatch.setattr("backend.executor.get_executor", lambda: _BoomExecutor())

    response = await client.post(
        "/api/v1/chat/confirm",
        json={
            "proposal": {
                "tool": "trigger_task",
                "args": {"source_id": source.id},
                "summary": "触发采集",
                "diff": "",
            }
        },
    )

    assert response.status_code == 502
    assert "派发失败" in response.json()["detail"]
    work_item = await db_session.scalar(select(OperationsWorkItem))
    assert work_item is not None
    assert work_item.status == WorkItemStatus.IN_PROGRESS
    assert work_item.evidence["execution"]["status"] == "failed_after_commit"


@pytest.mark.asyncio
async def test_viewer_confirmation_is_denied_without_mutation(client, db_session):
    provider = await _make_provider(db_session, default_model="gpt-4o-mini", enabled=True)
    await _authorize_chat(
        db_session,
        subject="chat-viewer",
        role=WorkspaceRole.VIEWER,
    )

    response = await client.post(
        "/api/v1/chat/confirm",
        json={
            "proposal": {
                "tool": "update_provider",
                "args": {"provider_id": provider.id, "enabled": False},
                "summary": "配置 AI 模型提供商",
                "diff": "enabled true -> false",
            }
        },
    )

    assert response.status_code == 403
    await db_session.refresh(provider)
    assert provider.enabled is True
    work_items = (await db_session.scalars(select(OperationsWorkItem))).all()
    assert work_items == []


@pytest.mark.asyncio
async def test_cross_workspace_confirmation_cannot_apply_recorded_proposal(
    client,
    db_session,
):
    provider = await _make_provider(db_session, default_model="gpt-4o-mini", enabled=True)
    identity_a, user_a, workspace_a = await _authorize_chat(
        db_session,
        subject="workspace-a-admin",
    )
    proposal = await _build_proposal(
        db_session,
        "update_provider",
        {"provider_id": provider.id, "enabled": False},
        identity=identity_a,
        workspace_id=workspace_a.id,
    )
    await db_session.commit()

    _, _, workspace_b = await _authorize_chat(
        db_session,
        subject="workspace-b-admin",
    )
    response = await client.post(
        "/api/v1/chat/confirm",
        json={"proposal": proposal.model_dump()},
    )

    assert response.status_code == 403
    await db_session.refresh(provider)
    assert provider.enabled is True
    work_item = await db_session.get(OperationsWorkItem, proposal.work_item_id)
    assert work_item is not None
    assert work_item.workspace_id == workspace_a.id
    assert work_item.workspace_id != workspace_b.id
    assert work_item.author_actor_id == user_a.id
    assert work_item.status == WorkItemStatus.OPEN
    assert work_item.evidence["schema_version"] == "agent-control-evidence/v1"
    assert work_item.evidence["proposal_version"] == proposal.proposal_version
    assert work_item.evidence["confirmation"]["state"] == "pending"


@pytest.mark.asyncio
async def test_confirmation_rejects_stale_target_version(client, db_session):
    provider = await _make_provider(db_session, default_model="gpt-4o-mini", enabled=True)
    identity, _, workspace = await _authorize_chat(db_session, subject="stale-proposal-admin")
    proposal = await _build_proposal(
        db_session,
        "update_provider",
        {"provider_id": provider.id, "enabled": False},
        identity=identity,
        workspace_id=workspace.id,
    )
    await db_session.commit()

    provider.default_model = "changed-after-proposal"
    await db_session.commit()

    response = await client.post(
        "/api/v1/chat/confirm",
        json={"proposal": proposal.model_dump()},
    )

    assert response.status_code == 409
    await db_session.refresh(provider)
    assert provider.enabled is True
    assert provider.default_model == "changed-after-proposal"
    work_item = await db_session.get(OperationsWorkItem, proposal.work_item_id)
    assert work_item is not None
    assert work_item.status == WorkItemStatus.OPEN
