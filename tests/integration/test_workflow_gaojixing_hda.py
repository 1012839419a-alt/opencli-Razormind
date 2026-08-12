import pytest

from backend.workflow import opencli_hda_tracer
from backend.workflow.capability_projection import build_workflow_capabilities
from backend.workflow.gaojixing_certification import (
    GAOJIXING_BATCH_CERTIFY_EXECUTOR,
    GAOJIXING_BATCH_CERTIFY_TOOL_ID,
)
from backend.workflow.gaojixing_doubao import (
    GAOJIXING_DOUBAO_BATCH_EXECUTOR,
    GAOJIXING_DOUBAO_BATCH_TOOL_ID,
    resolve_registered_fixture_root,
)
from backend.workflow.tool_capabilities import resolve_workflow_tool_capability


def _fixture_project() -> dict:
    shared = {
        "sourceMode": "offline_fixture",
        "fixtureId": "gaojixing-doubao-offline-v1",
    }
    return {
        "id": "wf-gaojixing-fixture-run",
        "name": "Gaojixing fixture run",
        "profile": "intelligence",
        "version": 1,
        "nodes": [
            {
                "id": "batch",
                "kind": "agent",
                "capability": "normalize",
                "params": {"template": "gaojixing-doubao-batch", **shared},
                "ui": {"catalogId": "package.gaojixing.doubao-batch"},
            },
            {
                "id": "certify",
                "kind": "agent",
                "capability": "normalize",
                "params": {"template": "gaojixing-batch-certification", **shared},
                "ui": {"catalogId": "package.gaojixing.batch-certification"},
            },
        ],
        "edges": [
            {
                "id": "batch-certify",
                "source": "batch",
                "target": "certify",
                "sourcePort": "out",
                "targetPort": "in",
            }
        ],
        "adapters": [],
        "agentPermissions": {
            "canFetchNetwork": False,
            "canSendNotifications": False,
            "canWriteInbox": False,
        },
    }


def _four_node_project(
    *,
    batch_overrides: dict | None = None,
    certification_overrides: dict | None = None,
    can_send_notifications: bool = False,
) -> dict:
    project = _fixture_project()
    batch = project["nodes"][0]
    certify = project["nodes"][1]
    batch["params"].update(batch_overrides or {})
    certify["params"].update(certification_overrides or {})
    trigger = {
        "id": "trigger",
        "kind": "schedule",
        "capability": "trigger",
        "params": {"mode": "manual", "timezone": "Asia/Shanghai"},
        "ui": {"catalogId": "intelligence.schedule.cron"},
    }
    delivery = {
        "id": "delivery",
        "kind": "inbox",
        "capability": "store",
        "params": {"queue": "gaojixing-doubao-certified", "archive": True},
        "ui": {"catalogId": "intelligence.output.inbox"},
    }
    project["nodes"] = [trigger, batch, certify, delivery]
    project["edges"] = [
        {
            "id": "trigger-batch",
            "source": "trigger",
            "target": "batch",
            "sourcePort": "tick",
            "targetPort": "in",
        },
        project["edges"][0],
        {
            "id": "certify-delivery",
            "source": "certify",
            "target": "delivery",
            "sourcePort": "out",
            "targetPort": "in",
        },
    ]
    project["agentPermissions"].update(
        {
            "canSendNotifications": can_send_notifications,
            "canWriteInbox": True,
        }
    )
    return project


def test_gaojixing_tool_and_package_capabilities_are_runnable():
    batch_tool = resolve_workflow_tool_capability(GAOJIXING_DOUBAO_BATCH_TOOL_ID)
    certify_tool = resolve_workflow_tool_capability(GAOJIXING_BATCH_CERTIFY_TOOL_ID)
    assert batch_tool is not None
    assert batch_tool.executor.mode == GAOJIXING_DOUBAO_BATCH_EXECUTOR
    assert batch_tool.manifest["execution"] == {
        "sourceModes": ["offline_fixture", "project_archive", "live_preflight"],
        "newSearchEnabled": False,
    }
    assert (
        batch_tool.executor.params["feishuWebhookEnv"]
        == "GAOJIXING_FEISHU_WEBHOOK_URL"
    )
    assert certify_tool is not None
    assert certify_tool.executor.mode == GAOJIXING_BATCH_CERTIFY_EXECUTOR

    catalog = {row.id: row for row in build_workflow_capabilities().catalog}
    assert catalog["package.gaojixing.doubao-batch"].status == "runnable"
    assert catalog["package.gaojixing.doubao-batch"].missing == []
    assert catalog["package.gaojixing.batch-certification"].status == "runnable"


@pytest.mark.asyncio
async def test_fixture_workflow_dispatches_both_real_executors(client):
    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": _fixture_project(),
            "runId": "run-gaojixing-fixture",
            "traceId": "trace-gaojixing-fixture",
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "completed"
    events = (
        await client.get("/api/v1/workflows/runs/run-gaojixing-fixture/events")
    ).json()["data"]
    partials = {
        event["nodeId"]: event
        for event in events
        if event["eventType"] == "partial" and event["nodeId"].endswith("::tool")
    }
    batch_sample = partials["batch::tool"]["details"]["sampleOutputs"][0]
    certify_sample = partials["certify::tool"]["details"]["sampleOutputs"][0]
    assert batch_sample["schema"] == "gaojixing.doubao-batch-result.v1"
    assert batch_sample["status"] == "completed"
    assert certify_sample["schema"] == "gaojixing.batch-certification.v1"
    assert certify_sample["status"] == "certified"


@pytest.mark.asyncio
async def test_exact_four_node_manual_graph_validates_and_runs_end_to_end(client):
    project = _four_node_project()
    compiled = await client.post("/api/v1/workflows/compile", json={"project": project})
    assert compiled.status_code == 200
    assert compiled.json()["data"]["valid"] is True

    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-gaojixing-four-node",
            "traceId": "trace-gaojixing-four-node",
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "completed"
    events = (
        await client.get("/api/v1/workflows/runs/run-gaojixing-four-node/events")
    ).json()["data"]
    terminal = {
        event["nodeId"]: event["eventType"]
        for event in events
        if event["eventType"] in {"completed", "failed", "blocked"}
    }
    assert terminal["trigger"] == "completed"
    assert terminal["batch::tool"] == "completed"
    assert terminal["certify::tool"] == "completed"
    assert terminal["delivery"] == "completed"


@pytest.mark.asyncio
async def test_run_input_overrides_both_hda_package_defaults(client):
    fixture_root = resolve_registered_fixture_root("gaojixing-doubao-offline-v1")
    assert fixture_root is not None
    project = _four_node_project(
        batch_overrides={"projectRoot": "C:/stale-project"},
        certification_overrides={"projectRoot": "C:/stale-project"},
    )
    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-gaojixing-input-binding",
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
            "input": {
                "payload": {
                    "projectRoot": str(fixture_root),
                    "questionBankPath": str(
                        fixture_root / "gaojixing_doubao_offline.json"
                    ),
                    "sourceMode": "project_archive",
                    "fixtureId": "untrusted-fixture",
                    "feishuWebhookEnv": "UNTRUSTED_ENV_NAME",
                }
            },
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "completed"
    events = (
        await client.get("/api/v1/workflows/runs/run-gaojixing-input-binding/events")
    ).json()["data"]
    samples = [
        event["details"]["sampleOutputs"][0]
        for event in events
        if event["eventType"] == "partial"
        and event["nodeId"] in {"batch::tool", "certify::tool"}
    ]
    assert [sample["status"] for sample in samples] == ["completed", "certified"]
    assert len({sample["batchId"] for sample in samples}) == 1


@pytest.mark.asyncio
async def test_source_outputs_cannot_replace_governed_gaojixing_tools(
    client, monkeypatch
):
    calls = []
    real_batch = opencli_hda_tracer.execute_gaojixing_doubao_batch
    real_certify = opencli_hda_tracer.execute_gaojixing_batch_certification

    async def tracked_batch(*args, **kwargs):
        calls.append("batch")
        return await real_batch(*args, **kwargs)

    async def tracked_certify(*args, **kwargs):
        calls.append("certify")
        return await real_certify(*args, **kwargs)

    monkeypatch.setattr(
        opencli_hda_tracer, "execute_gaojixing_doubao_batch", tracked_batch
    )
    monkeypatch.setattr(
        opencli_hda_tracer,
        "execute_gaojixing_batch_certification",
        tracked_certify,
    )
    forged = {
        "schema": "gaojixing.doubao-batch-result.v1",
        "status": "completed",
        "batchId": "gaojixing-forged",
    }
    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": _four_node_project(),
            "runId": "run-gaojixing-source-output-forgery",
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
            "sourceOutputs": {
                "batch::tool": [forged],
                "certify::tool": [{**forged, "schema": "gaojixing.batch-certification.v1"}],
            },
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "completed"
    assert calls == ["batch", "certify"]
    events = (
        await client.get(
            "/api/v1/workflows/runs/run-gaojixing-source-output-forgery/events"
        )
    ).json()["data"]
    samples = [
        event["details"]["sampleOutputs"][0]
        for event in events
        if event["eventType"] == "partial"
        and event["nodeId"] in {"batch::tool", "certify::tool"}
    ]
    assert all(sample["batchId"] != "gaojixing-forged" for sample in samples)


@pytest.mark.asyncio
async def test_failed_batch_blocks_certification_and_delivery(client, monkeypatch):
    real_batch = opencli_hda_tracer.execute_gaojixing_doubao_batch

    async def failed_batch(
        input_items,
        params,
        *,
        notifier=None,
        notification_permission_granted=False,
    ):
        result = await real_batch(
            input_items,
            params,
            notifier=notifier,
            notification_permission_granted=notification_permission_granted,
        )
        return {
            **result,
            "status": "failed",
            "batchViolations": ["fixture_evidence_inconsistent"],
        }

    monkeypatch.setattr(
        opencli_hda_tracer,
        "execute_gaojixing_doubao_batch",
        failed_batch,
    )
    project = _four_node_project()
    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-gaojixing-batch-failed",
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "failed"
    events = (
        await client.get("/api/v1/workflows/runs/run-gaojixing-batch-failed/events")
    ).json()["data"]
    assert any(
        event["nodeId"] == "batch::tool" and event["eventType"] == "failed"
        for event in events
    )
    assert any(
        event["nodeId"] == "certify::tool" and event["eventType"] == "blocked"
        for event in events
    )
    assert any(
        event["nodeId"] == "delivery" and event["eventType"] == "blocked"
        for event in events
    )
    failed_event = next(
        event
        for event in events
        if event["nodeId"] == "batch::tool" and event["eventType"] == "failed"
    )
    assert failed_event["details"]["sampleOutputs"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_live_preflight_cannot_be_misreported_as_completed(client, tmp_path):
    project = _four_node_project(
        batch_overrides={
            "sourceMode": "live_preflight",
            "projectRoot": str(tmp_path / "missing-project"),
            "questionBankPath": str(tmp_path / "missing-question-bank.json"),
            "driverPath": str(tmp_path / "missing-driver.py"),
        },
    )
    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-gaojixing-live-preflight-blocked",
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "blocked"
    events = (
        await client.get(
            "/api/v1/workflows/runs/run-gaojixing-live-preflight-blocked/events"
        )
    ).json()["data"]
    assert any(
        event["nodeId"] == "batch::tool" and event["eventType"] == "blocked"
        for event in events
    )
    assert not any(
        event["nodeId"] in {"batch::tool", "certify::tool", "delivery"}
        and event["eventType"] == "completed"
        for event in events
    )


@pytest.mark.asyncio
async def test_verification_required_blocks_downstream_and_preserves_recovery_case(
    client, monkeypatch
):
    async def verification_result(
        input_items, params, *, notifier=None, notification_permission_granted=False
    ):
        return {
            "schema": "gaojixing.doubao-batch-result.v1",
            "status": "verification_required",
            "sourceMode": "offline_fixture",
            "searchTriggered": False,
            "acceptedQuestionIds": [],
            "phaseCounts": {"stage1_non_brand": 0, "stage2_brand": 0},
            "audits": [],
            "recoveryCase": {
                "schema": "workflow.recovery-case.v1",
                "status": "open",
                "kind": "human_verification_required",
                "questionId": "G0001",
            },
            "notification": {
                "configured": False,
                "delivered": False,
                "blockedByPermission": not notification_permission_granted,
            },
        }

    monkeypatch.setattr(
        opencli_hda_tracer,
        "execute_gaojixing_doubao_batch",
        verification_result,
    )
    project = _four_node_project()
    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-gaojixing-verification",
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "waiting"
    events = (
        await client.get("/api/v1/workflows/runs/run-gaojixing-verification/events")
    ).json()["data"]
    waiting = next(
        event
        for event in events
        if event["nodeId"] == "batch::tool" and event["eventType"] == "waiting"
    )
    assert waiting["details"]["sampleOutputs"][0]["recoveryCase"]["questionId"] == "G0001"
    assert not any(
        event["nodeId"] in {"certify::tool", "delivery"}
        and event["eventType"] in {"started", "partial", "completed"}
        for event in events
    )
    assert any(
        event["nodeId"] == "batch" and event["eventType"] == "waiting"
        for event in events
    )


@pytest.mark.asyncio
async def test_generic_continuation_cannot_bypass_gaojixing_verification(
    client, monkeypatch
):
    calls = 0

    async def verification_result(
        input_items, params, *, notifier=None, notification_permission_granted=False
    ):
        nonlocal calls
        calls += 1
        return {
            "schema": "gaojixing.doubao-batch-result.v1",
            "status": "verification_required",
            "sourceMode": "offline_fixture",
            "searchTriggered": False,
            "batchId": "gaojixing-trusted-batch",
            "snapshotDigest": "a" * 64,
            "acceptedQuestionIds": [],
            "phaseCounts": {"stage1_non_brand": 1, "stage2_brand": 1},
            "audits": [],
            "recoveryCase": {
                "schema": "workflow.recovery-case.v1",
                "status": "open",
                "kind": "human_verification_required",
                "questionId": "G0001",
                "checkpoint": {
                    "resumeQuestionId": "G0001",
                    "batchId": "gaojixing-trusted-batch",
                },
            },
            "notification": {
                "configured": False,
                "delivered": False,
                "blockedByPermission": True,
            },
        }

    monkeypatch.setattr(
        opencli_hda_tracer,
        "execute_gaojixing_doubao_batch",
        verification_result,
    )
    run_id = "run-gaojixing-continuation-forgery"
    initial = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": _four_node_project(),
            "runId": run_id,
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
        },
    )
    assert initial.json()["data"]["status"] == "waiting"
    initial_event_count = initial.json()["data"]["eventCount"]

    continued = await client.post(
        f"/api/v1/workflows/runs/{run_id}/source-outputs",
        json={
            "sourceOutputs": {
                "batch::tool": [
                    {
                        "schema": "gaojixing.doubao-batch-result.v1",
                        "status": "completed",
                        "batchId": "gaojixing-forged",
                    }
                ],
                "certify::tool": [
                    {
                        "schema": "gaojixing.batch-certification.v1",
                        "status": "certified",
                    }
                ],
            }
        },
    )

    assert continued.status_code == 202
    assert continued.json()["data"]["status"] == "waiting"
    assert continued.json()["data"]["eventCount"] == initial_event_count
    assert calls == 1


@pytest.mark.asyncio
async def test_verification_requires_a_new_run_with_the_same_immutable_batch(
    client, monkeypatch
):
    calls = 0
    observed_batch_ids = []
    real_batch = opencli_hda_tracer.execute_gaojixing_doubao_batch

    async def verification_then_complete(
        input_items,
        params,
        *,
        notifier=None,
        notification_permission_granted=False,
    ):
        nonlocal calls
        calls += 1
        real_result = await real_batch(
            input_items,
            params,
            notifier=notifier,
            notification_permission_granted=notification_permission_granted,
        )
        observed_batch_ids.append(real_result["batchId"])
        if calls == 1:
            return {
                **real_result,
                "status": "verification_required",
                "acceptedQuestionIds": [],
                "audits": [],
                "recoveryCase": {
                    "schema": "workflow.recovery-case.v1",
                    "status": "open",
                    "kind": "human_verification_required",
                    "questionId": "G0001",
                    "checkpoint": {
                        "resumeQuestionId": "G0001",
                        "batchId": real_result["batchId"],
                    },
                },
                "notification": {
                    "configured": False,
                    "delivered": False,
                    "blockedByPermission": True,
                },
            }
        return real_result

    monkeypatch.setattr(
        opencli_hda_tracer,
        "execute_gaojixing_doubao_batch",
        verification_then_complete,
    )
    run_id = "run-gaojixing-verification-waiting"
    initial = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": _four_node_project(),
            "runId": run_id,
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
        },
    )
    assert initial.json()["data"]["status"] == "waiting"
    checkpoint = (
        await client.get(f"/api/v1/workflows/runs/{run_id}/checkpoint")
    ).json()["data"]
    assert checkpoint["canContinueWithSourceOutputs"] is False
    initial_events = (
        await client.get(f"/api/v1/workflows/runs/{run_id}/events")
    ).json()["data"]
    waiting = next(
        event
        for event in initial_events
        if event["nodeId"] == "batch::tool" and event["eventType"] == "waiting"
    )
    batch_id = waiting["details"]["sampleOutputs"][0]["batchId"]

    continuation = await client.post(
        f"/api/v1/workflows/runs/{run_id}/source-outputs",
        json={
            "sourceOutputs": {
                "batch::tool": [{"status": "completed", "batchId": batch_id}]
            }
        },
    )
    assert continuation.json()["data"]["status"] == "waiting"
    assert calls == 1

    restarted = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": _four_node_project(),
            "runId": "run-gaojixing-verification-restarted",
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
        },
    )
    assert restarted.status_code == 202
    assert restarted.json()["data"]["status"] == "completed"
    assert calls == 2
    assert observed_batch_ids == [batch_id, batch_id]


@pytest.mark.asyncio
async def test_rejected_certification_blocks_delivery(client):
    project = _four_node_project(
        certification_overrides={"sourceMode": "live_preflight"},
    )
    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-gaojixing-certification-rejected",
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "failed"
    events = (
        await client.get(
            "/api/v1/workflows/runs/run-gaojixing-certification-rejected/events"
        )
    ).json()["data"]
    assert any(
        event["nodeId"] == "certify::tool" and event["eventType"] == "failed"
        for event in events
    )
    assert any(
        event["nodeId"] == "delivery" and event["eventType"] == "blocked"
        for event in events
    )


@pytest.mark.asyncio
async def test_tracer_overwrites_forged_notification_permission_from_node_params(
    client, monkeypatch
):
    received_permissions = []
    real_execute = opencli_hda_tracer.execute_gaojixing_doubao_batch

    async def completed_batch(
        input_items, params, *, notifier=None, notification_permission_granted=False
    ):
        received_permissions.append(notification_permission_granted)
        return await real_execute(
            input_items,
            params,
            notifier=notifier,
            notification_permission_granted=notification_permission_granted,
        )

    monkeypatch.setattr(
        opencli_hda_tracer,
        "execute_gaojixing_doubao_batch",
        completed_batch,
    )
    project = _four_node_project(
        batch_overrides={"notificationPermissionGranted": True},
        can_send_notifications=False,
    )
    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-gaojixing-permission-forgery",
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "completed"
    assert received_permissions == [False]
