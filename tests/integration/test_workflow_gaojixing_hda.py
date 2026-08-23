import json

import pytest

from backend.config import get_settings
from backend.models.workflow_run import WorkflowRun
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
    assert batch_tool.executor.params["feishuWebhookEnv"] == "GAOJIXING_FEISHU_WEBHOOK_URL"
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
    events = (await client.get("/api/v1/workflows/runs/run-gaojixing-fixture/events")).json()[
        "data"
    ]
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
    events = (await client.get("/api/v1/workflows/runs/run-gaojixing-four-node/events")).json()[
        "data"
    ]
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
async def test_question_bank_upload_stages_a_run_without_exposing_server_paths(
    client, db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "gaojixing_run_storage_path", str(tmp_path))
    monkeypatch.setattr(
        "backend.workflow.gaojixing_worker_runtime.dispatch_collection_job",
        lambda _job_id: None,
    )
    project = _four_node_project(
        batch_overrides={"sourceMode": "project_archive"},
        certification_overrides={"sourceMode": "project_archive"},
    )
    question_bank = json.dumps(
        {
            "phase1": [{"id": "G0001", "question": "孕妇 DHA 怎么选？"}],
            "phase2": [],
        },
        ensure_ascii=False,
    ).encode("utf-8")

    response = await client.post(
        "/api/v1/workflows/runs/question-bank",
        data={
            "request": json.dumps(
                {
                    "project": project,
                    "traceId": "trace-managed-question-bank",
                    "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
                },
                ensure_ascii=False,
            ),
        },
        files={"questionBank": ("questions.json", question_bank, "application/json")},
    )

    assert response.status_code == 202, response.text
    response_data = response.json()["data"]
    assert response_data["status"] == "waiting"
    run_id = response_data["runId"]
    assert run_id != "run-managed-question-bank"
    assert str(tmp_path) not in response.text
    row = await db_session.get(WorkflowRun, run_id)
    assert row is not None
    assert set(row.request["input"]["payload"]) == {"questionBatchRef"}
    assert row.request["input"]["payload"]["questionBatchRef"].startswith("qbr1.")
    assert "projectRoot" not in response.text
    assert "questionBankPath" not in response.text
    stored_bank = tmp_path / "runs" / run_id / "question-bank.json"
    assert stored_bank.is_file()
    frozen_content = stored_bank.read_bytes()
    events = (
        await client.get(f"/api/v1/workflows/runs/{run_id}/events")
    ).json()["data"]
    batch_waiting = next(
        event
        for event in events
        if event["nodeId"] == "batch::tool" and event["eventType"] == "waiting"
    )
    # A live collection has been durably queued.  The public event deliberately
    # exposes only its governed job identity, not internal filesystem paths.
    assert "gaojixing.collection-run.v1" in json.dumps(
        batch_waiting["details"], ensure_ascii=False
    )
    assert "projectRoot" not in response.text
    assert "questionBankPath" not in response.text

    explicit = await client.post(
        "/api/v1/workflows/runs/question-bank",
        data={
            "request": json.dumps(
                {
                    "project": project,
                    "runId": run_id,
                    "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
                }
            )
        },
        files={
            "questionBank": (
                "questions.json",
                b'{"phase1":[{"id":"G0001","question":"changed"}],"phase2":[]}',
                "application/json",
            )
        },
    )
    assert explicit.status_code == 400, explicit.text
    assert stored_bank.read_bytes() == frozen_content


@pytest.mark.asyncio
async def test_internal_worker_resume_certifies_same_run_without_source_outputs(
    client, db_session, tmp_path, monkeypatch
):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from backend.models.gaojixing_collection import (
        GaojixingCollectionRun,
        GaojixingCollectionRunStatus,
    )
    from backend.workflow.gaojixing_collection_runner import run_collection_job

    monkeypatch.setattr(get_settings(), "gaojixing_run_storage_path", str(tmp_path))
    monkeypatch.setattr(
        "backend.workflow.gaojixing_worker_runtime.dispatch_collection_job",
        lambda _job_id: None,
    )
    project = _four_node_project(
        batch_overrides={"sourceMode": "project_archive"},
        certification_overrides={"sourceMode": "project_archive"},
    )
    question_bank = json.dumps(
        {
            "phase1": [{"id": "G0001", "question": "孕妇 DHA 怎么选？"}],
            "phase2": [],
        },
        ensure_ascii=False,
    ).encode()
    initial = await client.post(
        "/api/v1/workflows/runs/question-bank",
        data={
            "request": json.dumps(
                {
                    "project": project,
                    "traceId": "trace-managed-worker-resume",
                    "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
                }
            )
        },
        files={"questionBank": ("questions.json", question_bank, "application/json")},
    )
    assert initial.status_code == 202
    initial_data = initial.json()["data"]
    assert initial_data["status"] == "waiting"
    run_id = initial_data["runId"]
    job = await db_session.scalar(
        select(GaojixingCollectionRun).where(
            GaojixingCollectionRun.workflow_run_id == run_id
        )
    )
    assert job is not None
    job_id = job.id

    class Driver:
        def __init__(self, project_root):
            self.project_root = project_root

        async def preflight(self):
            return None

        async def collect(self, *, question_id, question):
            screenshots = []
            for suffix in ("01_顶部", "02_正文", "03_底部"):
                relative = f"screenshots/{question_id}_{suffix}.png"
                path = self.project_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(suffix.encode())
                screenshots.append(relative)
            return {
                "id": question_id,
                "question": question,
                "has_brand": False,
                "status": "completed",
                "chat_url": "https://www.doubao.com/chat/1234567890",
                "answer": "完整回答",
                "collected_at": "2026-08-12T10:00:00Z",
                "page_modules": {
                    "keywords": "页面未显示",
                    "ref_links": "页面未显示",
                    "product_links": "页面未显示",
                    "video_links": "页面未显示",
                    "followups": [f"{question}还有哪些注意事项？"],
                },
                "brand_observation": {
                    "target": "高吉星",
                    "appeared": False,
                    "positions": [],
                    "natural_recommendation": False,
                    "basis": "页面回答和已显示模块未出现高吉星",
                },
                "page_evidence": {
                    "screenshot_files": screenshots,
                    "share_link": {
                        "displayed": True,
                        "copy_control_displayed": True,
                        "capture_method": "share-copy-control",
                        "url": f"https://www.doubao.com/thread/fixture{question_id}",
                    },
                    "module_expectations": {
                        name: {
                            "displayed": name == "followups",
                            "expected_count": 1 if name == "followups" else 0,
                        }
                        for name in (
                            "keywords",
                            "ref_links",
                            "product_links",
                            "video_links",
                            "followups",
                        )
                    },
                    "screenshot_coverage": {
                        "top": True,
                        "answer": True,
                        "bottom": True,
                    },
                },
                "required_missing": [],
            }

        async def inspect_current(self, *, question_id, question):
            raise AssertionError("fresh job must not inspect")

    sessions = async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    from backend.workflow.opencli_hda_tracer import resume_gaojixing_workflow_run

    outcome = await run_collection_job(
        job_id,
        session_factory=sessions,
        driver_factory=Driver,
        schedule_resume=lambda run_id: resume_gaojixing_workflow_run(
            run_id, session=db_session
        ),
        storage_root=tmp_path,
        signing_key=get_settings().secret_key,
    )
    assert outcome == "workflow_resume_scheduled"
    await db_session.commit()

    projection = (await client.get(
        f"/api/v1/workflows/runs/{run_id}"
    )).json()["data"]
    assert projection["status"] == "completed"
    db_session.expire_all()
    completed = await db_session.get(GaojixingCollectionRun, job_id)
    assert completed is not None
    assert completed.status == GaojixingCollectionRunStatus.SUCCEEDED.value
    stored = await db_session.get(WorkflowRun, run_id)
    assert stored is not None
    assert stored.request["sourceOutputs"] == {}


@pytest.mark.asyncio
async def test_question_bank_upload_rejects_a_malformed_package_before_creating_a_run(
    client, db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "gaojixing_run_storage_path", str(tmp_path))

    response = await client.post(
        "/api/v1/workflows/runs/question-bank",
        data={
            "request": json.dumps(
                {
                    "project": _four_node_project(),
                }
            ),
        },
        files={
            "questionBank": (
                "questions.json",
                b'{"phase1": [{"id": "G0001", "question": "ok"}]}',
                "application/json",
            )
        },
    )

    assert response.status_code == 422, response.text
    assert "phase2" in response.text
    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())

    unsupported = await client.post(
        "/api/v1/workflows/runs/question-bank",
        data={"request": json.dumps({"project": _four_node_project()})},
        files={"questionBank": ("questions.csv", b"question", "text/csv")},
    )
    assert unsupported.status_code == 415, unsupported.text


@pytest.mark.asyncio
async def test_question_bank_upload_rejects_a_non_gaojixing_workflow(
    client, db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "gaojixing_run_storage_path", str(tmp_path))
    project = _four_node_project()
    project["nodes"] = [project["nodes"][0], project["nodes"][-1]]
    project["edges"] = []
    response = await client.post(
        "/api/v1/workflows/runs/question-bank",
        data={
            "request": json.dumps(
                {
                    "project": project,
                    "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
                }
            )
        },
        files={
            "questionBank": (
                "questions.json",
                b'{"phase1":[{"id":"G0001","question":"question"}],"phase2":[]}',
                "application/json",
            )
        },
    )

    assert response.status_code == 422, response.text
    assert "Gaojixing" in response.text
    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())


@pytest.mark.asyncio
async def test_question_bank_upload_rejects_client_run_id_without_staging(
    client, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "gaojixing_run_storage_path", str(tmp_path))
    response = await client.post(
        "/api/v1/workflows/runs/question-bank",
        data={
            "request": json.dumps(
                {
                    "project": _four_node_project(),
                    "runId": "existing-or-attacker-chosen-run",
                }
            )
        },
        files={
            "questionBank": (
                "questions.json",
                json.dumps(
                    {
                        "phase1": [{"id": "G0001", "question": "普通题"}],
                        "phase2": [],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert response.status_code == 400, response.text
    assert not (tmp_path / "runs").exists()


@pytest.mark.asyncio
async def test_question_bank_upload_cleans_unique_package_when_run_start_raises(
    client, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "gaojixing_run_storage_path", str(tmp_path))

    async def fail_to_start(*args, **kwargs):
        raise RuntimeError("run start failed")

    monkeypatch.setattr(
        "backend.api.v1.workflows.start_workflow_run",
        fail_to_start,
    )
    with pytest.raises(RuntimeError, match="run start failed"):
        await client.post(
            "/api/v1/workflows/runs/question-bank",
            data={"request": json.dumps({"project": _four_node_project()})},
            files={
                "questionBank": (
                    "questions.json",
                    json.dumps(
                        {
                            "phase1": [{"id": "G0001", "question": "普通题"}],
                            "phase2": [],
                        },
                        ensure_ascii=False,
                    ).encode("utf-8"),
                    "application/json",
                )
            },
        )

    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())


@pytest.mark.asyncio
async def test_run_input_cannot_override_governed_hda_configuration(client):
    project = _four_node_project()
    response = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-gaojixing-input-binding",
            "trigger": {"kind": "manual", "triggerNodeId": "trigger"},
            "input": {
                "payload": {
                    "projectRoot": "C:/attacker-controlled-project",
                    "questionBankPath": "C:/attacker-controlled-project/questions.json",
                    "sourceMode": "project_archive",
                    "fixtureId": "untrusted-fixture",
                    "feishuWebhookEnv": "UNTRUSTED_ENV_NAME",
                }
            },
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "completed"
    events = (await client.get("/api/v1/workflows/runs/run-gaojixing-input-binding/events")).json()[
        "data"
    ]
    samples = [
        event["details"]["sampleOutputs"][0]
        for event in events
        if event["eventType"] == "partial" and event["nodeId"] in {"batch::tool", "certify::tool"}
    ]
    assert [sample["status"] for sample in samples] == ["completed", "certified"]
    assert len({sample["batchId"] for sample in samples}) == 1


@pytest.mark.asyncio
async def test_source_outputs_cannot_replace_governed_gaojixing_tools(client, monkeypatch):
    calls = []
    real_batch = opencli_hda_tracer.execute_gaojixing_doubao_batch
    real_certify = opencli_hda_tracer.execute_gaojixing_batch_certification

    async def tracked_batch(*args, **kwargs):
        calls.append("batch")
        return await real_batch(*args, **kwargs)

    async def tracked_certify(*args, **kwargs):
        calls.append("certify")
        return await real_certify(*args, **kwargs)

    monkeypatch.setattr(opencli_hda_tracer, "execute_gaojixing_doubao_batch", tracked_batch)
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
        await client.get("/api/v1/workflows/runs/run-gaojixing-source-output-forgery/events")
    ).json()["data"]
    samples = [
        event["details"]["sampleOutputs"][0]
        for event in events
        if event["eventType"] == "partial" and event["nodeId"] in {"batch::tool", "certify::tool"}
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
    events = (await client.get("/api/v1/workflows/runs/run-gaojixing-batch-failed/events")).json()[
        "data"
    ]
    assert any(
        event["nodeId"] == "batch::tool" and event["eventType"] == "failed" for event in events
    )
    assert any(
        event["nodeId"] == "certify::tool" and event["eventType"] == "blocked" for event in events
    )
    assert any(
        event["nodeId"] == "delivery" and event["eventType"] == "blocked" for event in events
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
        await client.get("/api/v1/workflows/runs/run-gaojixing-live-preflight-blocked/events")
    ).json()["data"]
    assert any(
        event["nodeId"] == "batch::tool" and event["eventType"] == "blocked" for event in events
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
    events = (await client.get("/api/v1/workflows/runs/run-gaojixing-verification/events")).json()[
        "data"
    ]
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
    assert any(event["nodeId"] == "batch" and event["eventType"] == "waiting" for event in events)


@pytest.mark.asyncio
async def test_generic_continuation_cannot_bypass_gaojixing_verification(client, monkeypatch):
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
async def test_verification_requires_a_new_run_with_the_same_immutable_batch(client, monkeypatch):
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
    checkpoint = (await client.get(f"/api/v1/workflows/runs/{run_id}/checkpoint")).json()["data"]
    assert checkpoint["canContinueWithSourceOutputs"] is False
    initial_events = (await client.get(f"/api/v1/workflows/runs/{run_id}/events")).json()["data"]
    waiting = next(
        event
        for event in initial_events
        if event["nodeId"] == "batch::tool" and event["eventType"] == "waiting"
    )
    batch_id = waiting["details"]["sampleOutputs"][0]["batchId"]

    continuation = await client.post(
        f"/api/v1/workflows/runs/{run_id}/source-outputs",
        json={"sourceOutputs": {"batch::tool": [{"status": "completed", "batchId": batch_id}]}},
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
        await client.get("/api/v1/workflows/runs/run-gaojixing-certification-rejected/events")
    ).json()["data"]
    assert any(
        event["nodeId"] == "certify::tool" and event["eventType"] == "failed" for event in events
    )
    assert any(
        event["nodeId"] == "delivery" and event["eventType"] == "blocked" for event in events
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
