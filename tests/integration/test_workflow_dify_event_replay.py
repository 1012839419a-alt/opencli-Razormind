from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.v1.dify_imports import get_dify_graphon_client
from backend.database import commit_session, get_db
from backend.main import app
from backend.schemas.dify_compat import DifyRuntimeEventPage, DifyRuntimeRunStart
from backend.workflow.opencli_hda_tracer import _RUNS

FIXTURE = Path(__file__).parents[1] / "fixtures" / "dify" / "pure_logic.yml"
GRAPHON_COMMIT = "b187ce7927fea1a7c137b642be3f78e3abb9f7de"


class DurableReplayGraphonClient:
    timeout_seconds = 1.0

    async def inspect(self, **_kwargs):
        return {
            "loadStatus": "ready",
            "loadReason": None,
            "engine": {
                "name": "graphon",
                "version": "0.7.0",
                "commit": GRAPHON_COMMIT,
            },
            "appMode": "workflow",
            "nodes": [
                {"sourceNodeId": "source-start-001", "type": "start", "status": "ready"},
                {"sourceNodeId": "source-end-002", "type": "end", "status": "ready"},
            ],
            "dependencies": [],
            "blockers": [],
        }

    async def start_run(self, **_kwargs):
        return DifyRuntimeRunStart.model_validate(
            {
                "contractVersion": "opencli.graphon.compat.v1",
                "runtimeRunId": "durable-replay-runtime",
                "status": "queued",
                "eventsUrl": "/v1/dify/runs/durable-replay-runtime/events",
            }
        )

    async def replay_events(self, runtime_run_id: str, *, after_sequence: int):
        assert runtime_run_id == "durable-replay-runtime"
        if after_sequence == 0:
            events = [
                {
                    "sequence": 1,
                    "eventType": "node_started",
                    "nodeId": "source-start-001",
                    "payload": {},
                },
                {
                    "sequence": 2,
                    "eventType": "node_completed",
                    "nodeId": "source-start-001",
                    "payload": {"outputs": {"started": True}},
                },
            ]
            status = "running"
        else:
            events = [
                {
                    "sequence": 3,
                    "eventType": "node_started",
                    "nodeId": "source-end-002",
                    "payload": {},
                },
                {
                    "sequence": 4,
                    "eventType": "node_completed",
                    "nodeId": "source-end-002",
                    "payload": {"outputs": {"answer": "done"}},
                },
                {
                    "sequence": 5,
                    "eventType": "graph_completed",
                    "payload": {"outputs": {"answer": "done"}},
                },
            ]
            status = "completed"
        return DifyRuntimeEventPage.model_validate(
            {
                "contractVersion": "opencli.graphon.compat.v1",
                "runtimeRunId": runtime_run_id,
                "status": status,
                "nextSequence": events[-1]["sequence"],
                "events": events,
            }
        )

    async def cancel_run(self, _runtime_run_id: str):
        raise AssertionError("completed runs must not be cancelled")


@pytest.fixture
def durable_replay_graphon_client():
    graphon = DurableReplayGraphonClient()
    app.dependency_overrides[get_dify_graphon_client] = lambda: graphon
    yield graphon
    app.dependency_overrides.pop(get_dify_graphon_client, None)
    _RUNS.clear()


@pytest.mark.asyncio
async def test_dify_projection_and_events_reload_from_a_fresh_database_session(
    db_engine,
    durable_replay_graphon_client,
):
    session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session
            await commit_session(session)

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as first_process:
            imported = await first_process.post(
                "/api/v1/workflows/import/dify",
                json={"source": FIXTURE.read_text(encoding="utf-8")},
            )
            assert imported.status_code == 200
            project = imported.json()["data"]["project"]

            started = await first_process.post(
                "/api/v1/workflows/runs",
                json={"project": project, "runId": "dify-durable-replay"},
            )
            assert started.status_code == 202
            initial_projection = (
                await first_process.get("/api/v1/workflows/runs/dify-durable-replay")
            ).json()["data"]
            initial_events = (
                await first_process.get(
                    "/api/v1/workflows/runs/dify-durable-replay/events"
                )
            ).json()["data"]

        # A new request client and a new SQLAlchemy session must not rely on
        # the process-local _RUNS mirror for either projection or replay.
        _RUNS.clear()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as restarted_process:
            reloaded_projection = (
                await restarted_process.get("/api/v1/workflows/runs/dify-durable-replay")
            ).json()["data"]
            reloaded_events = (
                await restarted_process.get(
                    "/api/v1/workflows/runs/dify-durable-replay/events"
                )
            ).json()["data"]
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert reloaded_projection == initial_projection
    assert reloaded_events == initial_events
    assert [event["sequence"] for event in reloaded_events] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert {
        event["internalNodeId"]
        for event in reloaded_events
        if len(event["nodePath"]) == 2
    } == {"source-start-001", "source-end-002"}
