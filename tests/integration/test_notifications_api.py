"""Integration tests for /api/v1/notifications endpoints."""

import hashlib
import hmac
import json

import pytest


@pytest.fixture
def rule_data():
    return {
        "name": "Test Webhook Rule",
        "trigger_event": "on_new_record",
        "notifier_type": "webhook",
        "notifier_config": {"url": "https://hooks.example.com/test"},
        "enabled": True,
    }


@pytest.mark.asyncio
async def test_list_rules_empty(client):
    response = await client.get("/api/v1/notifications/rules")
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_create_rule(client, rule_data):
    response = await client.post("/api/v1/notifications/rules", json=rule_data)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == "Test Webhook Rule"
    assert data["notifier_type"] == "webhook"


@pytest.mark.asyncio
async def test_get_rule(client, rule_data):
    create_resp = await client.post("/api/v1/notifications/rules", json=rule_data)
    rule_id = create_resp.json()["data"]["id"]

    response = await client.get(f"/api/v1/notifications/rules/{rule_id}")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == rule_id


@pytest.mark.asyncio
async def test_get_rule_not_found(client):
    response = await client.get("/api/v1/notifications/rules/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_rule(client, rule_data):
    create_resp = await client.post("/api/v1/notifications/rules", json=rule_data)
    rule_id = create_resp.json()["data"]["id"]

    response = await client.patch(
        f"/api/v1/notifications/rules/{rule_id}",
        json={"name": "Updated Rule", "enabled": False},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "Updated Rule"
    assert data["enabled"] is False


@pytest.mark.asyncio
async def test_delete_rule(client, rule_data):
    create_resp = await client.post("/api/v1/notifications/rules", json=rule_data)
    rule_id = create_resp.json()["data"]["id"]

    delete_resp = await client.delete(f"/api/v1/notifications/rules/{rule_id}")
    assert delete_resp.status_code == 200

    get_resp = await client.get(f"/api/v1/notifications/rules/{rule_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_list_logs_empty(client):
    response = await client.get("/api/v1/notifications/logs")
    assert response.status_code == 200
    assert response.json()["data"] == []


def _signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.mark.asyncio
async def test_ack_notification_log_updates_log_and_record(client, db_session):
    from backend.models.notification import NotificationLog, NotificationRule
    from backend.models.record import CollectedRecord
    from backend.models.source import DataSource
    from backend.models.task import CollectionTask

    source = DataSource(
        name="Ack API Source",
        channel_type="rss",
        channel_config={"feed_url": "https://ex.com/feed"},
    )
    db_session.add(source)
    await db_session.flush()

    task = CollectionTask(source_id=source.id, trigger_type="manual", parameters={})
    db_session.add(task)
    await db_session.flush()

    record = CollectedRecord(
        task_id=task.id,
        source_id=source.id,
        raw_data={"title": "Ack me"},
        normalized_data={"title": "Ack me"},
        content_hash="ack-api-hash",
        status="normalized",
    )
    db_session.add(record)

    rule = NotificationRule(
        name="Ack Rule",
        trigger_event="on_new_record",
        notifier_type="webhook",
        notifier_config={"url": "https://hooks.ex.com", "ack_secret": "ack-secret"},
        enabled=True,
    )
    db_session.add(rule)
    await db_session.flush()

    log = NotificationLog(
        rule_id=rule.id,
        record_id=record.id,
        status="sent",
        ack_status="pending",
    )
    db_session.add(log)
    await db_session.flush()

    body = {"status": "acked", "ack_data": {"consumer": "n8n", "run_id": "run-1"}}
    raw_body = json.dumps(body, separators=(",", ":")).encode()
    response = await client.post(
        f"/api/v1/notifications/logs/{log.id}/ack",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Signature-256": _signature("ack-secret", raw_body),
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ack_status"] == "acked"
    assert data["ack_data"] == {"consumer": "n8n", "run_id": "run-1"}

    await db_session.refresh(record)
    assert record.status == "notified"


@pytest.mark.asyncio
async def test_ack_notification_log_rejects_bad_signature(client, db_session):
    from backend.models.notification import NotificationLog, NotificationRule

    rule = NotificationRule(
        name="Protected Ack Rule",
        trigger_event="on_new_record",
        notifier_type="webhook",
        notifier_config={"url": "https://hooks.ex.com", "ack_secret": "ack-secret"},
        enabled=True,
    )
    db_session.add(rule)
    await db_session.flush()

    log = NotificationLog(rule_id=rule.id, status="sent", ack_status="pending")
    db_session.add(log)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/notifications/logs/{log.id}/ack",
        json={"status": "acked", "ack_data": {"consumer": "n8n"}},
        headers={"X-Signature-256": "sha256=bad"},
    )

    assert response.status_code == 401
    await db_session.refresh(log)
    assert log.ack_status == "pending"
