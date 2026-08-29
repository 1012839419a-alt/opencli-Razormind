"""Highest scoped Admin/III seam tests for the durable collection vertical."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.models.iii_collection import (
    IIICollectionAttemptV1,
    IIICollectionCommandV1,
    IIICollectionLifecycleObservationV1,
    IIICollectionOutboundV1,
)
from backend.models.studio import (
    StudioProject,
    StudioWorkflow,
    StudioWorkflowValidationRun,
    StudioWorkflowVersion,
    StudioWorkspace,
)
from backend.models.workflow_run import WorkflowRun, WorkflowRunEvent
from backend.schemas.iii_collection import IIICollectionRequestV1
from backend.workflow.iii_collection_dispatch import (
    IIIBridgeUnavailableError,
    collector_trigger_payload,
    dispatch_collection_attempt,
)
from backend.workflow.iii_collection_store import (
    CollectionScope,
    _attempt_and_outbound,
    cancel_collection,
    submit_collection,
)


async def _create_scoped_run(db_session):
    workspace = StudioWorkspace(id="iii-workspace", name="III", slug="iii")
    project = StudioProject(
        id="iii-project",
        workspace_id=workspace.id,
        name="III Project",
        slug="iii-project",
        created_by_user_id="operator",
    )
    workflow = StudioWorkflow(id="iii-workflow", project_id=project.id, name="III Workflow")
    validation = StudioWorkflowValidationRun(
        id="iii-validation",
        workflow_id=workflow.id,
        draft_revision=1,
        status="valid",
        valid=True,
        errors=[],
        warnings=[],
        compile_version="v1",
        resolved_graph={"nodes": [{"id": "opencli-source"}]},
    )
    version = StudioWorkflowVersion(
        id="iii-version",
        workflow_id=workflow.id,
        version=1,
        draft_revision=1,
        graph={"nodes": [{"id": "opencli-source"}]},
        compile_version="v1",
        validation_run_id=validation.id,
        published_by_user_id="operator",
        reason="test",
    )
    run = WorkflowRun(
        id="iii-run",
        workflow_id=workflow.id,
        studio_workflow_version_id=version.id,
        trace_id="iii-trace",
        status="queued",
        request={},
        projection={},
    )
    db_session.add_all([workspace, project, workflow, validation, version, run])
    await db_session.commit()
    return {
        "workspace": workspace,
        "project": project,
        "workflow": workflow,
        "version": version,
        "run": run,
    }


def _route(scope: dict) -> str:
    return (
        f"/api/v1/workspaces/{scope['workspace'].id}/projects/{scope['project'].id}"
        f"/workflows/{scope['workflow'].id}/runs/{scope['run'].id}/iii-collections"
    )


def _submit_body() -> dict:
    return {
        "version": "v1",
        "idempotencyKey": "collection-key",
        "nodeId": "opencli-source",
        "collection": {
            "site": "bilibili",
            "command": "search",
            "args": {"keyword": "AI"},
            "sourceBindingId": "binding-1",
            "sourceBindingRevisionId": "binding-revision-1",
            "sourceBindingRevisionNumber": 1,
        },
    }


@pytest.mark.asyncio
async def test_submit_commits_admin_ledger_before_iii_trigger(client, db_session, monkeypatch):
    scope = await _create_scoped_run(db_session)
    calls: list[dict] = []
    commits = 0
    original_commit = db_session.commit

    async def commit_with_boundary() -> None:
        nonlocal commits
        commits += 1
        await original_commit()

    monkeypatch.setattr(db_session, "commit", commit_with_boundary)


    async def fake_dispatch(db, *, command):
        attempt = (
            await db.execute(
                select(IIICollectionAttemptV1).where(IIICollectionAttemptV1.command_id == command.id)
            )
        ).scalar_one()
        outbound = (
            await db.execute(select(IIICollectionOutboundV1).where(IIICollectionOutboundV1.attempt_id == attempt.id))
        ).scalar_one()
        event = (
            await db.execute(select(WorkflowRunEvent).where(WorkflowRunEvent.run_id == command.run_id))
        ).scalar_one()
        assert commits == 1
        assert outbound.state == "pending"
        assert event.payload["details"]["iiiCollection"]["stage"] == "admin_requested"
        payload = collector_trigger_payload(command, attempt)
        assert payload["task_id"] == attempt.task_id
        assert payload["trace_id"] == scope["run"].trace_id
        assert payload["admin_collection"]["payload_sha256"] == command.payload_sha256
        calls.append(payload)
        return outbound

    monkeypatch.setattr("backend.api.v1.iii_collections.dispatch_collection_attempt", fake_dispatch)
    response = await client.post(_route(scope), json=_submit_body())

    assert response.status_code == 202
    data = response.json()["data"]
    assert data["created"] is True
    assert len(calls) == 1
    assert calls[0]["site"] == "bilibili"
    assert calls[0]["command"] == "search"


@pytest.mark.asyncio
async def test_pending_resume_reuses_same_attempt_and_precommit_failure_never_dispatches(
    db_session, monkeypatch
):
    scope_rows = await _create_scoped_run(db_session)
    scope = CollectionScope(
        workspace_id=scope_rows["workspace"].id,
        project_id=scope_rows["project"].id,
        workflow_id=scope_rows["workflow"].id,
        studio_workflow_version_id=scope_rows["version"].id,
        run_id=scope_rows["run"].id,
    )
    collection = IIICollectionRequestV1(
        site="bilibili",
        command="search",
        args={"keyword": "AI"},
    )
    submitted = await submit_collection(
        db_session,
        scope=scope,
        run=scope_rows["run"],
        node_id="opencli-source",
        idempotency_key="restart-key",
        collection=collection,
    )
    captured: list[dict] = []

    async def fake_invoke(payload, *, function_id):
        assert function_id == "odp.collect::opencli_snapshot"
        captured.append(payload)

    monkeypatch.setattr("backend.workflow.iii_collection_dispatch.invoke_iii_collection", fake_invoke)
    resumed = await dispatch_collection_attempt(db_session, command=submitted.command)
    assert resumed.state == "submitted_to_iii"
    assert len(captured) == 1
    assert captured[0]["task_id"] == submitted.attempt.task_id
    assert captured[0]["admin_collection"]["attempt_id"] == submitted.attempt.id
    assert captured[0]["admin_collection"]["payload_sha256"] == submitted.command.payload_sha256

    before = len(captured)
    with pytest.raises(Exception):
        await submit_collection(
            db_session,
            scope=CollectionScope(
                workspace_id=scope.workspace_id,
                project_id=scope.project_id,
                workflow_id=scope.workflow_id,
                studio_workflow_version_id=scope.studio_workflow_version_id,
                run_id="missing-run",
            ),
            run=scope_rows["run"],
            node_id="opencli-source",
            idempotency_key="precommit-failure",
            collection=collection,
        )
    await db_session.rollback()
    assert len(captured) == before


@pytest.mark.asyncio
async def test_lifecycle_replay_conflict_unavailable_status_and_redaction(client, db_session, monkeypatch):
    scope = await _create_scoped_run(db_session)
    monkeypatch.setattr(
        "backend.api.v1.iii_collections.get_settings",
        lambda: SimpleNamespace(iii_lifecycle_token="bridge-token"),
    )
    lifecycle_headers = {"x-iii-bridge-token": "bridge-token"}


    async def unavailable(_payload, *, function_id):
        assert function_id == "odp.collect::opencli_snapshot"
        raise IIIBridgeUnavailableError("offline")

    monkeypatch.setattr("backend.workflow.iii_collection_dispatch.invoke_iii_collection", unavailable)
    submit_response = await client.post(_route(scope), json=_submit_body())
    assert submit_response.status_code == 202
    submit = submit_response.json()["data"]
    command = await db_session.get(IIICollectionCommandV1, submit["commandId"])
    assert command is not None
    attempt = await db_session.get(IIICollectionAttemptV1, submit["attemptId"])
    assert attempt is not None
    unavailable_status = await client.get(f"{_route(scope)}/{command.id}")
    assert unavailable_status.status_code == 200
    assert unavailable_status.json()["data"]["state"] == "bridge_unavailable"
    assert unavailable_status.json()["data"]["recoveryAction"] == "resume_dispatch"


    lifecycle = {
        "version": "v1",
        "workspace_id": command.workspace_id,
        "project_id": command.project_id,
        "workflow_id": command.workflow_id,
        "studio_workflow_version_id": command.studio_workflow_version_id,
        "run_id": command.run_id,
        "node_id": command.node_id,
        "command_id": command.id,
        "attempt_id": attempt.id,
        "attempt_number": attempt.attempt_number,
        "task_id": attempt.task_id,
        "trace_id": attempt.trace_id,
        "source_id": command.odp_source_id,
        "source_binding_id": command.source_binding_id,
        "source_binding_revision_id": command.source_binding_revision_id,
        "source_binding_revision_number": command.source_binding_revision_number,
        "payload_sha256": command.payload_sha256,
        "sequence": 1,
        "event_type": "bridge_accepted",
        "summary": {},
    }
    first = await client.post(
        "/api/v1/iii-collections/lifecycle", json=lifecycle, headers=lifecycle_headers
    )
    assert first.status_code == 200
    assert first.json()["data"]["duplicate"] is False
    replay = await client.post(
        "/api/v1/iii-collections/lifecycle", json=lifecycle, headers=lifecycle_headers
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["duplicate"] is True
    changed = {**lifecycle, "summary": {"items_fetched": 1}}
    conflict = await client.post(
        "/api/v1/iii-collections/lifecycle", json=changed, headers=lifecycle_headers
    )
    assert conflict.status_code == 409
    started = {
        **lifecycle,
        "sequence": 2,
        "event_type": "collector_started",
    }
    returned = {
        **lifecycle,
        "sequence": 3,
        "event_type": "collector_returned",
        "summary": {"items_fetched": 0},
    }
    assert (
        await client.post(
            "/api/v1/iii-collections/lifecycle", json=started, headers=lifecycle_headers
        )
    ).status_code == 200
    assert (
        await client.post(
            "/api/v1/iii-collections/lifecycle", json=returned, headers=lifecycle_headers
        )
    ).status_code == 200


    status_response = await client.get(f"{_route(scope)}/{command.id}")
    assert status_response.status_code == 200
    vertical = status_response.json()["data"]
    assert vertical["state"] == "collector_returned"
    assert vertical["blockingStage"] == "reconciliation"
    assert vertical["recoveryAction"] == "await_reconciliation"
    assert vertical["sideEffectUncertainty"] is True
    rendered = status_response.text
    assert "bilibili" not in rendered
    assert "keyword" not in rendered
    assert "admin_command_json" not in rendered
    persisted = (
        await db_session.execute(
            select(IIICollectionLifecycleObservationV1).where(
                IIICollectionLifecycleObservationV1.command_id == command.id
            )
        )
    ).scalars().all()
    assert len(persisted) == 3


@pytest.mark.asyncio
async def test_cancellation_before_dispatch_never_invokes_iii(db_session, monkeypatch):
    scope_rows = await _create_scoped_run(db_session)
    scope = CollectionScope(
        workspace_id=scope_rows["workspace"].id,
        project_id=scope_rows["project"].id,
        workflow_id=scope_rows["workflow"].id,
        studio_workflow_version_id=scope_rows["version"].id,
        run_id=scope_rows["run"].id,
    )
    submitted = await submit_collection(
        db_session,
        scope=scope,
        run=scope_rows["run"],
        node_id="opencli-source",
        idempotency_key="cancel-key",
        collection=IIICollectionRequestV1(site="bilibili", command="search"),
    )
    await cancel_collection(db_session, command=submitted.command)
    invoked = False

    async def should_not_invoke(_payload, *, function_id):
        nonlocal invoked
        invoked = True

    monkeypatch.setattr("backend.workflow.iii_collection_dispatch.invoke_iii_collection", should_not_invoke)
    outbound = await dispatch_collection_attempt(db_session, command=submitted.command)
    assert outbound.state == "cancelled"
    assert invoked is False


@pytest.mark.asyncio
async def test_lifecycle_ingress_requires_bridge_token_and_rejects_scope_hash_conflicts(
    client, db_session, monkeypatch
):
    scope = await _create_scoped_run(db_session)

    async def no_dispatch(_db, *, command):
        _, outbound = await _attempt_and_outbound(_db, command.id)
        return outbound

    monkeypatch.setattr("backend.api.v1.iii_collections.dispatch_collection_attempt", no_dispatch)
    monkeypatch.setattr(
        "backend.api.v1.iii_collections.get_settings",
        lambda: SimpleNamespace(iii_lifecycle_token="bridge-token"),
    )
    submitted = await client.post(_route(scope), json=_submit_body())
    assert submitted.status_code == 202
    command = await db_session.get(IIICollectionCommandV1, submitted.json()["data"]["commandId"])
    attempt = await db_session.get(IIICollectionAttemptV1, submitted.json()["data"]["attemptId"])
    assert command is not None and attempt is not None
    lifecycle = {
        "version": "v1",
        "workspace_id": command.workspace_id,
        "project_id": command.project_id,
        "workflow_id": command.workflow_id,
        "studio_workflow_version_id": command.studio_workflow_version_id,
        "run_id": command.run_id,
        "node_id": command.node_id,
        "command_id": command.id,
        "attempt_id": attempt.id,
        "attempt_number": attempt.attempt_number,
        "task_id": attempt.task_id,
        "trace_id": attempt.trace_id,
        "source_id": command.odp_source_id,
        "source_binding_id": command.source_binding_id,
        "source_binding_revision_id": command.source_binding_revision_id,
        "source_binding_revision_number": command.source_binding_revision_number,
        "payload_sha256": command.payload_sha256,
        "sequence": 1,
        "event_type": "bridge_accepted",
        "summary": {},
    }

    monkeypatch.setattr(
        "backend.api.v1.iii_collections.get_settings",
        lambda: SimpleNamespace(iii_lifecycle_token=""),
    )
    assert (await client.post("/api/v1/iii-collections/lifecycle", json=lifecycle)).status_code == 401
    monkeypatch.setattr(
        "backend.api.v1.iii_collections.get_settings",
        lambda: SimpleNamespace(iii_lifecycle_token="bridge-token"),
    )
    assert (await client.post("/api/v1/iii-collections/lifecycle", json=lifecycle)).status_code == 401
    assert (
        await client.post(
            "/api/v1/iii-collections/lifecycle",
            json=lifecycle,
            headers={"x-iii-bridge-token": "wrong-token"},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/iii-collections/lifecycle",
            json=lifecycle,
            headers={"x-iii-bridge-token": "bridge-token"},
        )
    ).status_code == 200

    wrong_hash = {**lifecycle, "sequence": 2, "event_type": "collector_started", "payload_sha256": "0" * 64}
    assert (
        await client.post(
            "/api/v1/iii-collections/lifecycle",
            json=wrong_hash,
            headers={"x-iii-bridge-token": "bridge-token"},
        )
    ).status_code == 409
    assert (
        await client.get(
            f"/api/v1/workspaces/other/projects/{scope['project'].id}/workflows/"
            f"{scope['workflow'].id}/runs/{scope['run'].id}/iii-collections/{command.id}"
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/workspaces/{scope['workspace'].id}/projects/{scope['project'].id}/workflows/"
            f"{scope['workflow'].id}/runs/other-run/iii-collections/{command.id}"
        )
    ).status_code == 404
