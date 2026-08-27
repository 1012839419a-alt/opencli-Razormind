from fastapi import HTTPException

from backend import ws_agent_manager
from backend.api.v1 import internal_agent_runs
from backend.models import (
    EdgeNode,
    OperationsAgentIdentity,
    OperationsAgentRun,
    PublishedOperationsAgentVersion,
    Team,
    User,
    Workspace,
)


async def _seed_run(db_session, *, status: str) -> OperationsAgentRun:
    user = User(subject=f"internal-dispatch-{status}")
    workspace = Workspace(name=f"Internal {status}", slug=f"internal-{status}")
    db_session.add_all((user, workspace))
    await db_session.flush()
    team = Team(workspace_id=workspace.id, name="Operations", slug="operations")
    db_session.add(team)
    await db_session.flush()
    agent = OperationsAgentIdentity(
        workspace_id=workspace.id,
        owning_team_id=team.id,
        name=f"Internal {status}",
        current_profile_version=1,
        current_published_version=1,
    )
    db_session.add(agent)
    await db_session.flush()
    db_session.add(
        PublishedOperationsAgentVersion(
            operations_agent_id=agent.id,
            version=1,
            draft_revision=1,
            instructions="Read only",
            model_configuration={
                "agent_contract": {
                    "schema_version": "agent.contract.v2",
                    "role": "scheduled_reviewer",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "state_schema": {"type": "object"},
                    "required_capabilities": ["streaming"],
                    "tool_policy": {},
                    "budget": {},
                    "quality_gates": [],
                    "evidence_requirements": [],
                },
                "runtime_binding": {
                    "schema_version": "agent.runtime-binding.v2",
                    "workflow": "builtin.read_only_readiness",
                    "preferred_agent_urls": ["http://internal-agent:19823"],
                    "preferred_runtimes": ["miniflow"],
                    "model_binding": None,
                    "config": {"timeout_seconds": 60},
                    "dispatch_timeout_seconds": 60,
                },
            },
            tool_configuration={},
            published_by_user_id=user.id,
            reason="Internal dispatch test",
        )
    )
    db_session.add(
        EdgeNode(
            url="http://internal-agent:19823",
            label="Internal runtime",
            protocol="ws",
            mode="cdp",
            node_type="docker",
            status="online",
            runtimes=["miniflow"],
            runtime_capabilities={"miniflow": ["streaming"]},
        )
    )
    run = OperationsAgentRun(
        workspace_id=workspace.id,
        operations_agent_id=agent.id,
        published_version=1,
        profile_version=1,
        trigger_type="scheduled",
        target_resource_type="automation",
        target_resource_id="automation-test",
        input_payload={},
        state_payload={},
        status=status,
        started_by_user_id=user.id,
    )
    db_session.add(run)
    await db_session.commit()
    return run


def _use_session(db_session, monkeypatch) -> None:
    class SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(internal_agent_runs, "AsyncSessionLocal", SessionContext)


async def test_terminal_run_returns_without_connected_agent(db_session, monkeypatch):
    run = await _seed_run(db_session, status="completed")
    _use_session(db_session, monkeypatch)
    monkeypatch.setattr(ws_agent_manager, "is_connected", lambda _url: False)
    scheduled = []
    monkeypatch.setattr(internal_agent_runs, "schedule_operations_agent_run", scheduled.append)

    response = await internal_agent_runs.dispatch_scheduled_agent_run(run.id)

    assert response.data.status == "completed"
    assert scheduled == []


async def test_queued_run_stays_queued_when_agent_disconnected(db_session, monkeypatch):
    run = await _seed_run(db_session, status="queued")
    _use_session(db_session, monkeypatch)
    monkeypatch.setattr(ws_agent_manager, "is_connected", lambda _url: False)
    scheduled = []
    monkeypatch.setattr(internal_agent_runs, "schedule_operations_agent_run", scheduled.append)

    try:
        await internal_agent_runs.dispatch_scheduled_agent_run(run.id)
    except HTTPException as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("disconnected queued run must return 503")
    assert scheduled == []
    await db_session.refresh(run)
    assert run.status == "queued"


async def test_running_duplicate_returns_without_dispatch(db_session, monkeypatch):
    run = await _seed_run(db_session, status="running")
    _use_session(db_session, monkeypatch)
    monkeypatch.setattr(ws_agent_manager, "is_connected", lambda _url: False)
    scheduled = []
    monkeypatch.setattr(internal_agent_runs, "schedule_operations_agent_run", scheduled.append)

    response = await internal_agent_runs.dispatch_scheduled_agent_run(run.id)

    assert response.data.status == "running"
    assert scheduled == []


async def test_connected_queued_run_is_scheduled_without_waiting(db_session, monkeypatch):
    run = await _seed_run(db_session, status="queued")
    _use_session(db_session, monkeypatch)
    monkeypatch.setattr(ws_agent_manager, "is_connected", lambda _url: True)
    scheduled = []
    monkeypatch.setattr(internal_agent_runs, "schedule_operations_agent_run", scheduled.append)

    response = await internal_agent_runs.dispatch_scheduled_agent_run(run.id)

    assert response.data.status == "queued"
    assert scheduled == [run.id]
    assert response.data.execution_binding["runtime"] == "miniflow"
