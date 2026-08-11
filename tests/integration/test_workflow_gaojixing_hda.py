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
)
from backend.workflow.tool_capabilities import resolve_workflow_tool_capability


def _fixture_project() -> dict:
    shared = {
        "sourceMode": "offline_fixture",
        "fixtureId": "gaojixing-doubao-offline-v1",
        "phase1Expected": 1,
        "phase2Expected": 1,
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
async def test_failed_batch_blocks_certification_and_delivery(client):
    project = _four_node_project(batch_overrides={"phase2Expected": 2})
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
async def test_rejected_certification_blocks_delivery(client):
    project = _four_node_project(
        certification_overrides={"phase2Expected": 2},
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
