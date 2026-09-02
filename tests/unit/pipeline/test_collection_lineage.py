"""Focused P0-1 collection lineage propagation tests."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.models.notification import NotificationLog, NotificationRule
from backend.models.record import CollectedRecord
from backend.models.source import DataSource
from backend.models.task import CollectionTask
from backend.notifiers.base import NotificationPayload
from backend.pipeline.notifier_dispatch import dispatch_notifications
from backend.pipeline.sinks import CollectionLineage, LegacyDbSink, RunContext


@pytest.mark.asyncio
async def test_run_context_lineage_persists_on_legacy_record(db_session):
    source = DataSource(
        name="Lineage Source",
        channel_type="unknown",
        channel_config={},
    )
    db_session.add(source)
    await db_session.flush()
    task = CollectionTask(source_id=source.id, parameters={})
    db_session.add(task)
    await db_session.flush()

    ctx = RunContext(
        task_id=task.id,
        source_id=source.id,
        provider="unknown",
        run_id="task-run-1",
        trace_id="trace-1",
        source_revision_id="source-revision-1",
        source_binding_revision_id="binding-revision-1",
        worker_id="worker-1",
        runtime_id="runtime-1",
        trace_ref="trace-artifact-1",
        artifact_refs=[{"kind": "raw", "ref": "artifact-1"}],
    )
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=db_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.database.AsyncSessionLocal", return_value=session_cm):
        result = await LegacyDbSink().write_batch(
            ctx,
            [{"title": "Attributed", "url": "https://example.test/item"}],
        )

    assert result.accepted == 1
    record = (await db_session.execute(select(CollectedRecord))).scalar_one()
    assert record.lineage == {
        "task_id": task.id,
        "source_id": source.id,
        "provider": "unknown",
        "ingest_mode": "snapshot",
        "collection_run_id": "task-run-1",
        "acquisition_execution_id": None,
        "source_revision_id": "source-revision-1",
        "source_binding_revision_id": "binding-revision-1",
        "account_revision_id": None,
        "credential_revision_id": None,
        "project_id": None,
        "scope_ref": None,
        "worker_id": "worker-1",
        "runtime_id": "runtime-1",
        "trace_id": "trace-1",
        "trace_ref": "trace-artifact-1",
        "artifact_refs": [{"kind": "raw", "ref": "artifact-1"}],
    }


@pytest.mark.asyncio
async def test_notification_payload_and_log_keep_record_lineage(db_session):
    source = DataSource(name="Notify Source", channel_type="rss", channel_config={})
    db_session.add(source)
    await db_session.flush()
    task = CollectionTask(source_id=source.id, parameters={})
    db_session.add(task)
    await db_session.flush()
    record = CollectedRecord(
        task_id=task.id,
        source_id=source.id,
        raw_data={"title": "raw"},
        normalized_data={"title": "normalized"},
        content_hash="lineage-notification-hash",
        status="normalized",
        lineage=CollectionLineage(
            task_id=task.id,
            source_id=source.id,
            collection_run_id="task-run-2",
            acquisition_execution_id="acquisition-2",
            trace_id="trace-2",
            artifact_refs=("artifact-2",),
        ).to_dict(),
    )
    db_session.add(record)
    rule = NotificationRule(
        name="Lineage Rule",
        trigger_event="on_new_record",
        notifier_type="webhook",
        notifier_config={},
        enabled=True,
    )
    db_session.add(rule)
    await db_session.flush()

    notifier = AsyncMock()
    notifier.send = AsyncMock(return_value=True)
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=db_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("backend.pipeline.notifier_dispatch.get_notifier", return_value=notifier),
        patch("backend.database.AsyncSessionLocal", return_value=session_cm),
    ):
        outcome = await dispatch_notifications(db_session, source.id, [record])

    assert outcome == {"sent": 1, "failed": 0}
    payload = notifier.send.await_args.args[1]
    assert isinstance(payload, NotificationPayload)
    assert payload.lineage == record.lineage
    log = (await db_session.execute(select(NotificationLog))).scalar_one()
    assert log.lineage == record.lineage


@pytest.mark.asyncio
async def test_pre_lineage_record_remains_readable(db_session):
    source = DataSource(name="Legacy Source", channel_type="rss", channel_config={})
    db_session.add(source)
    await db_session.flush()
    task = CollectionTask(source_id=source.id, parameters={})
    db_session.add(task)
    await db_session.flush()
    record = CollectedRecord(
        task_id=task.id,
        source_id=source.id,
        raw_data={},
        normalized_data={},
        content_hash="legacy-null-lineage-hash",
        status="normalized",
    )
    db_session.add(record)
    await db_session.flush()

    loaded = await db_session.get(CollectedRecord, record.id)
    assert loaded is not None
    assert loaded.lineage is None
