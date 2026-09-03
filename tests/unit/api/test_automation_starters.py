import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.api.v1.automations import router
from backend.database import Base, get_db
from backend.models.automation import Automation
from backend.models.identity import User, Workspace, WorkspaceMembership, WorkspaceRole
from backend.schemas.automation import AutomationCreate
from backend.security.identity import RequestIdentity, get_request_identity
from backend.services.automation_starter_service import install_starters


def test_ordinary_automation_create_rejects_starter_key():
    with pytest.raises(ValidationError):
        AutomationCreate.model_validate(
            {
                "name": "manual automation",
                "prompt": "Do the work",
                "executor": "codex",
                "schedule": "daily@09:00",
                "starter_key": "daily-run-brief",
            }
        )


async def _authorized_client(db_session, *, role=WorkspaceRole.ADMIN, subject="starter-admin"):
    user = User(subject=subject)
    workspace = Workspace(name=f"Starter {subject}", slug=f"starter-{subject}")
    db_session.add_all((user, workspace))
    await db_session.flush()
    db_session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role=role))
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
        await db_session.scalars(select(Automation).where(Automation.workspace_id == workspace.id))
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


@pytest.mark.asyncio
async def test_concurrent_first_install_is_idempotent_on_file_sqlite(tmp_path):
    database_path = tmp_path / "starters.sqlite"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as seed_session:
            user = User(subject="starter-concurrent")
            workspace = Workspace(name="Concurrent starters", slug="starter-concurrent")
            seed_session.add_all((user, workspace))
            await seed_session.commit()
            workspace_id = workspace.id
            user_id = user.id

        async def install_once():
            async with session_factory() as session:
                result = await install_starters(
                    session,
                    workspace_id=workspace_id,
                    created_by_user_id=user_id,
                )
                await session.commit()
                return result

        results = await asyncio.gather(install_once(), install_once())

        async with session_factory() as verify_session:
            rows = (
                await verify_session.scalars(
                    select(Automation).where(Automation.workspace_id == workspace_id)
                )
            ).all()
        assert len(rows) == 3
        assert sum(result.created_count for result in results) == 3
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_starter_install_requires_manage_agent_permission(db_session):
    app, workspace, _ = await _authorized_client(
        db_session, role=WorkspaceRole.VIEWER, subject="starter-viewer"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/workspaces/{workspace.id}/automations/starters/install")

    assert response.status_code == 403
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(Automation)
            .where(Automation.workspace_id == workspace.id)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_failed_starter_pack_rolls_back_all_rows(db_session, monkeypatch):
    user = User(subject="starter-failure")
    workspace = Workspace(name="Starter failure", slug="starter-failure")
    db_session.add_all((user, workspace))
    await db_session.flush()
    workspace_id = workspace.id

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
            workspace_id=workspace_id,
            created_by_user_id=user.id,
        )

    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(Automation)
            .where(Automation.workspace_id == workspace_id)
        )
        == 0
    )
