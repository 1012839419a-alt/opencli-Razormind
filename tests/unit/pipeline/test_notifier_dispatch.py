"""Unit tests for notifier_dispatch."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.notifiers.base import NotificationSendResult
from backend.pipeline.notifier_dispatch import dispatch_notifications


@pytest.mark.asyncio
async def test_dispatch_empty_records(db_session):
    await dispatch_notifications(db_session, "src-1", [], "on_new_record")
    # Should return without doing anything


@pytest.mark.asyncio
async def test_dispatch_no_matching_rules(db_session):
    record = MagicMock()
    record.id = "rec-1"
    record.normalized_data = {"title": "Test"}
    record.ai_enrichment = None

    # No rules in DB - should succeed silently
    await dispatch_notifications(db_session, "src-1", [record], "on_new_record")


@pytest.mark.asyncio
async def test_dispatch_with_matching_rule(db_session):
    from backend.models.notification import NotificationRule
    from backend.models.source import DataSource

    source = DataSource(
        name="Notif Source",
        channel_type="rss",
        channel_config={"feed_url": "https://ex.com/feed"},
    )
    db_session.add(source)
    await db_session.flush()

    rule = NotificationRule(
        name="Test Rule",
        trigger_event="on_new_record",
        notifier_type="webhook",
        notifier_config={"url": "https://hooks.ex.com"},
        enabled=True,
    )
    db_session.add(rule)
    await db_session.flush()

    record = MagicMock()
    record.id = "rec-1"
    record.normalized_data = {"title": "Test"}
    record.ai_enrichment = None

    mock_notifier = AsyncMock()
    mock_notifier.send = AsyncMock(return_value=True)

    with patch("backend.pipeline.notifier_dispatch.get_notifier", return_value=mock_notifier):
        await dispatch_notifications(db_session, source.id, [record], "on_new_record")

    mock_notifier.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_records_delivery_id_and_response_for_ack(db_session):
    from backend.models.notification import NotificationLog, NotificationRule
    from backend.models.source import DataSource

    source = DataSource(
        name="Ack Source",
        channel_type="rss",
        channel_config={"feed_url": "https://ex.com/feed"},
    )
    db_session.add(source)
    await db_session.flush()

    rule = NotificationRule(
        name="Ack Webhook",
        trigger_event="on_new_record",
        notifier_type="webhook",
        notifier_config={"url": "https://hooks.ex.com", "ack_secret": "ack-secret"},
        enabled=True,
    )
    db_session.add(rule)
    await db_session.flush()

    record = MagicMock()
    record.id = "rec-ack-1"
    record.normalized_data = {"title": "Needs ack"}
    record.ai_enrichment = None

    mock_notifier = AsyncMock()
    mock_notifier.send = AsyncMock(
        return_value=NotificationSendResult(
            success=True,
            response_data={"status_code": 202, "body": "queued"},
        )
    )

    with patch("backend.pipeline.notifier_dispatch.get_notifier", return_value=mock_notifier):
        await dispatch_notifications(db_session, source.id, [record], "on_new_record")

    payload = mock_notifier.send.await_args.args[1]
    assert payload.delivery_id

    result = await db_session.execute(select(NotificationLog))
    log = result.scalar_one()
    assert log.id == payload.delivery_id
    assert log.status == "sent"
    assert log.ack_status == "pending"
    assert log.response_data == {"status_code": 202, "body": "queued"}
