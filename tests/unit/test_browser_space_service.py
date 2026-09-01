"""Unit coverage for the Browser Space ownership and lease boundary."""

import pytest

from backend.models.browser import BrowserBinding, BrowserInstance
from backend.models.identity import User, Workspace, WorkspaceMembership, WorkspaceRole
from backend.services import browser_space_service as service


async def _seed(db_session, suffix: str = "one"):
    user = User(subject=f"operator-{suffix}")
    workspace = Workspace(name=f"Workspace {suffix}", slug=f"space-{suffix}")
    instance = BrowserInstance(endpoint=f"http://chrome-{suffix}:9222")
    db_session.add_all((user, workspace, instance))
    await db_session.flush()
    db_session.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=WorkspaceRole.OPERATOR,
        )
    )
    await db_session.commit()
    return user, workspace, instance


@pytest.mark.asyncio
async def test_create_space_validates_owner_binding_and_instance_reservation(db_session):
    user, workspace, instance = await _seed(db_session)
    binding = BrowserBinding(browser_endpoint=instance.endpoint, site="example.test")
    db_session.add(binding)
    await db_session.commit()

    space = await service.create_space(
        db_session,
        workspace_id=workspace.id,
        browser_instance_id=instance.id,
        binding_id=binding.id,
        owner_type="operator",
        owner_id=user.subject,
        granted_capabilities=["snapshot"],
    )

    assert space.workspace_id == workspace.id
    assert space.owner_id == user.subject
    assert space.status == "idle"
    with pytest.raises(service.BrowserSpaceServiceError, match="browser_instance_in_use"):
        await service.create_space(
            db_session,
            workspace_id=workspace.id,
            browser_instance_id=instance.id,
            owner_type="operator",
            owner_id=user.subject,
            granted_capabilities=["snapshot"],
        )


@pytest.mark.asyncio
async def test_submit_is_idempotent_serialized_and_redacts_results(db_session):
    user, workspace, instance = await _seed(db_session)
    space = await service.create_space(
        db_session,
        workspace_id=workspace.id,
        browser_instance_id=instance.id,
        owner_type="operator",
        owner_id=user.subject,
        granted_capabilities=["snapshot"],
    )
    calls = 0

    async def executor(_, capability, args):
        nonlocal calls
        calls += 1
        assert capability == "snapshot"
        assert args == {"selector": "body", "authorization": "secret"}
        return {"html": "<body>private</body>", "cookie": "secret", "title": "safe"}

    task = await service.submit_task(
        db_session,
        workspace_id=workspace.id,
        space_id=space.id,
        request_id="once",
        capability="snapshot",
        args={"selector": "body", "authorization": "secret"},
        executor=executor,
    )
    replay = await service.submit_task(
        db_session,
        workspace_id=workspace.id,
        space_id=space.id,
        request_id="once",
        capability="snapshot",
        args={},
    )

    assert task.status == "completed"
    assert task.result == {"html": "[redacted]", "cookie": "[redacted]", "title": "safe"}
    assert task.args["authorization"] == "[redacted]"
    assert replay.id == task.id
    assert calls == 1


@pytest.mark.asyncio
async def test_second_queued_task_is_rejected_and_cancellation_is_idempotent(db_session):
    user, workspace, instance = await _seed(db_session)
    space = await service.create_space(
        db_session,
        workspace_id=workspace.id,
        browser_instance_id=instance.id,
        owner_type="operator",
        owner_id=user.subject,
        granted_capabilities=["snapshot"],
    )
    queued = await service.submit_task(
        db_session,
        workspace_id=workspace.id,
        space_id=space.id,
        request_id="first",
        capability="snapshot",
        args={},
    )
    with pytest.raises(service.BrowserSpaceServiceError, match="space_task_in_progress"):
        await service.submit_task(
            db_session,
            workspace_id=workspace.id,
            space_id=space.id,
            request_id="second",
            capability="snapshot",
            args={},
        )

    cancelled = await service.cancel_space_task(
        db_session, workspace_id=workspace.id, space_id=space.id
    )
    repeated = await service.cancel_space_task(
        db_session, workspace_id=workspace.id, space_id=space.id
    )
    events = await service.list_events(db_session, workspace_id=workspace.id, space_id=space.id)

    assert cancelled is not None and cancelled.id == queued.id
    assert cancelled.status == "cancelled"
    assert repeated is not None and repeated.id == queued.id
    assert [event.kind for event in events] == ["queued", "cancel_requested", "cancelled"]
    assert [event.sequence for event in events] == [1, 2, 3]


@pytest.mark.asyncio
async def test_close_releases_reservation_and_rejects_new_tasks(db_session):
    user, workspace, instance = await _seed(db_session)
    space = await service.create_space(
        db_session,
        workspace_id=workspace.id,
        browser_instance_id=instance.id,
        owner_type="operator",
        owner_id=user.subject,
        granted_capabilities=["snapshot"],
    )
    closed = await service.close_space(db_session, workspace_id=workspace.id, space_id=space.id)
    assert closed.status == "closed"
    with pytest.raises(service.BrowserSpaceServiceError, match="browser_space_closed"):
        await service.submit_task(
            db_session,
            workspace_id=workspace.id,
            space_id=space.id,
            request_id="after-close",
            capability="snapshot",
            args={},
        )

    replacement = await service.create_space(
        db_session,
        workspace_id=workspace.id,
        browser_instance_id=instance.id,
        owner_type="operator",
        owner_id=user.subject,
        granted_capabilities=["snapshot"],
    )
    assert replacement.id != space.id
