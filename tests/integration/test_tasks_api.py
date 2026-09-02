"""Integration tests for /api/v1/tasks endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.task import CollectionTask


@pytest.mark.asyncio
async def test_list_tasks_empty(client):
    response = await client.get("/api/v1/tasks")
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_get_task_not_found(client):
    response = await client.get("/api/v1/tasks/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_trigger_task_source_not_found(client):
    response = await client.post(
        "/api/v1/tasks/trigger",
        json={"source_id": "nonexistent", "parameters": {}},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_trigger_task_disabled_source(client, sample_source_data):
    disabled_data = {**sample_source_data, "enabled": False}
    create_resp = await client.post("/api/v1/sources", json=disabled_data)
    source_id = create_resp.json()["data"]["id"]

    response = await client.post(
        "/api/v1/tasks/trigger",
        json={"source_id": source_id, "parameters": {}},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_trigger_task_success(client, sample_source_data):
    create_resp = await client.post("/api/v1/sources", json=sample_source_data)
    source_id = create_resp.json()["data"]["id"]

    with patch("backend.pipeline.runner.run_collection_pipeline", new=AsyncMock()):
        response = await client.post(
            "/api/v1/tasks/trigger",
            json={"source_id": source_id, "parameters": {"limit": 10}},
        )

    assert response.status_code == 202
    data = response.json()["data"]
    assert "task_id" in data


@pytest.mark.asyncio
async def test_list_task_runs(client, sample_source_data):
    create_resp = await client.post("/api/v1/sources", json=sample_source_data)
    source_id = create_resp.json()["data"]["id"]

    mock_result = MagicMock()
    mock_result.id = "celery-abc"

    with patch("backend.worker.tasks.run_collection") as mock_task:
        mock_task.apply_async.return_value = mock_result
        trigger_resp = await client.post(
            "/api/v1/tasks/trigger",
            json={"source_id": source_id},
        )

    task_id = trigger_resp.json()["data"]["task_id"]
    response = await client.get(f"/api/v1/tasks/{task_id}/runs")
    assert response.status_code == 200
    # No runs yet (Celery didn't actually execute)
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_recover_failed_task_is_lineaged_and_idempotent(
    client, db_session, sample_source_data
):
    create_resp = await client.post("/api/v1/sources", json=sample_source_data)
    source_id = create_resp.json()["data"]["id"]
    failed = CollectionTask(
        source_id=source_id,
        trigger_type="manual",
        parameters={"limit": 10},
        status="failed",
        error_message="collector timeout",
    )
    db_session.add(failed)
    await db_session.commit()
    await db_session.refresh(failed)

    executor = MagicMock()
    executor.dispatch_collection = AsyncMock(return_value={"task_id": "recovery"})
    with patch("backend.executor.get_executor", return_value=executor):
        first = await client.post(
            f"/api/v1/tasks/{failed.id}/recover",
            json={
                "idempotency_key": "recover-once",
                "reason": "recollect after timeout",
                "initiating_actor": "operator:test",
            },
        )
        replay = await client.post(
            f"/api/v1/tasks/{failed.id}/recover",
            json={
                "idempotency_key": "recover-once",
                "reason": "ignored on replay",
            },
        )

    assert first.status_code == 202
    assert replay.status_code == 202
    first_data = first.json()["data"]
    replay_data = replay.json()["data"]
    assert first_data["retry_of_task_id"] == failed.id
    assert replay_data["task_id"] == first_data["task_id"]
    assert replay_data["idempotency_replayed"] is True
    assert executor.dispatch_collection.await_count == 1

    recovery = await db_session.get(CollectionTask, first_data["task_id"])
    assert recovery.retry_of_task_id == failed.id
    assert recovery.recovery_reason == "recollect after timeout"
    assert recovery.initiating_actor == "operator:test"


@pytest.mark.asyncio
async def test_recover_nonterminal_task_is_rejected(client, db_session, sample_source_data):
    create_resp = await client.post("/api/v1/sources", json=sample_source_data)
    task = CollectionTask(
        source_id=create_resp.json()["data"]["id"],
        trigger_type="manual",
        status="running",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    response = await client.post(
        f"/api/v1/tasks/{task.id}/recover",
        json={"idempotency_key": "recover-running", "reason": "not allowed"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_tasks_filter_by_source(client, sample_source_data):
    create_resp = await client.post("/api/v1/sources", json=sample_source_data)
    source_id = create_resp.json()["data"]["id"]

    mock_result = MagicMock()
    mock_result.id = "celery-abc"
    with patch("backend.worker.tasks.run_collection") as mock_task:
        mock_task.apply_async.return_value = mock_result
        await client.post("/api/v1/tasks/trigger", json={"source_id": source_id})

    response = await client.get(f"/api/v1/tasks?source_id={source_id}")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1
