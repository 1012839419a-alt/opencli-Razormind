import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from backend.api.v1.automations import router
from backend.database import get_db
from backend.models.automation import Automation
from backend.models.identity import User, Workspace, WorkspaceMembership, WorkspaceRole
from backend.security.identity import RequestIdentity, get_request_identity
from backend.services.automation_starter_service import install_starters


async def _authorized_client(db_session, *, role=WorkspaceRole.ADMIN, subject="starter-admin"):
    user = User(subject=subject)
    workspace = Workspace(name=f"Starter {subject}", slug=f"starter-{subject}")
    db_session.add_all((user, workspace))
    await db_session.flush()
    db_session.add(
        WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role=role)
    )
    await db_session.commit()

    app = FastAPI()
    app.include_router(router)

    async def override_db():
        yield db_session

    async def override_identity():
        return RequestIdentity(subject=subject)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_request_identity] = override_identity
    return app, workspace, user


@pytest.mark.asyncio
async def test_install_starters_is_idempotent_and_stores_metadata(db_session):
    app, workspace, user = await _authorized_client(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(f"/workspaces/{workspace.id}/automations/starters/install")
        second = await client.post(f"/workspaces/{workspace.id}/automations/starters/install")

    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["created_count"] == 3
    assert first.json()["data"]["skipped_count"] == 0
    assert second.json()["data"]["created_count"] == 0
    assert second.json()["data"]["skipped_count"] == 3
    rows = (
        await db_session.scalars(
            select(Automation).where(Automation.workspace_id == workspace.id)
        )
    ).all()
    assert {row.starter_key for row in rows} == {
        "daily-run-brief",
        "weekly-system-review",
        "anomaly-follow-up",
    }
    assert all(row.executor == "codex" for row in rows)
    assert all(row.approval_mode == "suggest_changes" for row in rows)
    assert all(row.project["starter_key"] == row.starter_key for row in rows)
    assert all(row.project["lineage"] == "first-party-agent-starter" for row in rows)
    assert all(row.created_by_user_id == user.id for row in rows)
    assert all(row.enabled is False for row in rows)
    assert {row.schedule for row in rows} == {
        "daily@09:00",
        "weekly@09:00",
        "weekdays@09:00",
    }


@pytest.mark.asyncio
async def test_starter_install_requires_manage_agent_permission(db_session):
    app, workspace, _ = await _authorized_client(
        db_session, role=WorkspaceRole.VIEWER, subject="starter-viewer"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/workspaces/{workspace.id}/automations/starters/install")

    assert response.status_code == 403
    assert await db_session.scalar(
        select(func.count()).select_from(Automation).where(Automation.workspace_id == workspace.id)
    ) == 0


@pytest.mark.asyncio
async def test_failed_starter_pack_rolls_back_all_rows(db_session, monkeypatch):
    user = User(subject="starter-failure")
    workspace = Workspace(name="Starter failure", slug="starter-failure")
    db_session.add_all((user, workspace))
    await db_session.flush()

    original_flush = db_session.flush
    calls = 0

    async def fail_on_second_flush(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated starter failure")
        return await original_flush(*args, **kwargs)

    monkeypatch.setattr(db_session, "flush", fail_on_second_flush)
    with pytest.raises(RuntimeError, match="simulated starter failure"):
        await install_starters(
            db_session,
            workspace_id=workspace.id,
            created_by_user_id=user.id,
        )

    assert await db_session.scalar(
        select(func.count()).select_from(Automation).where(Automation.workspace_id == workspace.id)
    ) == 0
