"""Integration tests for the dashboard endpoint."""

import pytest

from backend.models.notification import NotificationLog, NotificationRule
from backend.models.record import CollectedRecord
from backend.models.task import CollectionTask


@pytest.mark.asyncio
async def test_dashboard_stats(client):
    response = await client.get("/api/v1/dashboard/stats")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "sources" in data
    assert "tasks" in data
    assert "records" in data
    assert "recent_runs" in data
    assert data["sources"]["total"] == 0


@pytest.mark.asyncio
async def test_dashboard_stats_with_source(client, sample_source_data):
    await client.post("/api/v1/sources", json=sample_source_data)
    response = await client.get("/api/v1/dashboard/stats")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sources"]["total"] == 1
    assert data["sources"]["enabled"] == 1


@pytest.mark.asyncio
async def test_opinion_monitor_projects_ai_and_configured_delivery_evidence(
    client, db_session, sample_source_data
):
    source_response = await client.post(
        "/api/v1/sources",
        json={
            **sample_source_data,
            "name": "Aibase 热点",
            "channel_type": "opencli",
            "channel_config": {"site": "aibase", "command": "news", "args": {"limit": 1}},
            "tags": ["opinion"],
        },
    )
    source_id = source_response.json()["data"]["id"]

    task = CollectionTask(source_id=source_id, trigger_type="manual", status="completed")
    db_session.add(task)
    await db_session.flush()

    record = CollectedRecord(
        task_id=task.id,
        source_id=source_id,
        raw_data={"title": "AI 新闻", "url": "https://example.com/news"},
        normalized_data={"title": "AI 新闻", "url": "https://example.com/news"},
        ai_enrichment={
            "summary": "国产模型热度上升",
            "tags": ["AI", "融资"],
            "sentiment": "positive",
        },
        content_hash="opinion-monitor-hash",
        status="ai_processed",
    )
    db_session.add(record)
    await db_session.flush()

    rule = NotificationRule(
        name="飞书舆情群",
        source_id=source_id,
        trigger_event="on_new_record",
        notifier_type="feishu",
        notifier_config={"webhook_url": "https://open.feishu.cn/example"},
        enabled=True,
    )
    db_session.add(rule)
    await db_session.flush()

    db_session.add(NotificationLog(rule_id=rule.id, record_id=record.id, status="sent"))
    email_rule = NotificationRule(
        name="邮件值班组",
        source_id=source_id,
        trigger_event="on_new_record",
        notifier_type="email",
        notifier_config={"recipients": ["ops@example.com"]},
        enabled=True,
    )
    db_session.add(email_rule)
    await db_session.flush()
    db_session.add(NotificationLog(rule_id=email_rule.id, record_id=record.id, status="failed"))
    await db_session.commit()

    response = await client.get("/api/v1/dashboard/opinion-monitor?range=all")
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["summary"]["records"] == 1
    assert data["summary"]["ai_processed"] == 1
    assert data["summary"]["notification_sent"] == 1
    assert data["summary"]["notification_failed"] == 1
    assert data["summary"]["active_notification_rules"] == 2
    assert data["summary"]["active_notification_channels"] == ["email", "feishu"]
    assert data["tags"] == [{"label": "AI", "count": 1}, {"label": "融资", "count": 1}]
    assert data["sentiment"] == [{"label": "positive", "count": 1}]
    assert data["recent"][0]["summary"] == "国产模型热度上升"
    assert data["recent"][0]["notification_status"] == "sent"
    assert data["recent"][0]["notification_channels"] == ["email", "feishu"]
    assert data["sources"][0]["notification_sent"] == 1
    assert data["sources"][0]["notification_failed"] == 1


@pytest.mark.asyncio
async def test_dashboard_delivery_summary_separates_submission_and_ack_evidence(
    client, db_session
):
    rule = NotificationRule(
        name="delivery summary rule",
        trigger_event="on_new_record",
        notifier_type="webhook",
        notifier_config={"url": "https://example.test/hook"},
        enabled=True,
    )
    db_session.add(rule)
    await db_session.flush()
    db_session.add_all(
        [
            NotificationLog(rule_id=rule.id, status="sent", ack_status="pending"),
            NotificationLog(rule_id=rule.id, status="sent", ack_status="acked"),
            NotificationLog(rule_id=rule.id, status="sent", ack_status="not_required"),
            NotificationLog(rule_id=rule.id, status="failed", ack_status="not_required"),
        ]
    )
    await db_session.commit()

    response = await client.get("/api/v1/dashboard/stats")
    assert response.status_code == 200
    delivery = response.json()["data"]["delivery"]
    assert delivery == {
        "attempts": 4,
        "submitted": 3,
        "awaiting_ack": 1,
        "confirmed": 1,
        "ack_failed": 0,
        "submission_failed": 1,
        "ack_not_required": 1,
        "window": "all",
        "since": None,
        "until": None,
    }
