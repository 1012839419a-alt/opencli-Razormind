import json
import re

import pytest
from sqlalchemy import select

from backend.models.record import CollectedRecord
from backend.models.source import DataSource
from backend.models.task import CollectionTask
from backend.schemas.workflow import CompiledWorkflowNode, WorkflowProject
from backend.workflow.compiler import compile_workflow_project
from backend.workflow.gaojixing_certification import (
    _evidence_digest,
    execute_gaojixing_batch_certification,
)
from backend.workflow.gaojixing_doubao import (
    audit_gaojixing_question_evidence,
    build_gaojixing_batch_snapshot,
    execute_gaojixing_doubao_batch,
)
from backend.workflow.hda_templates import materialize_hda_templates
from backend.workflow.opencli_hda_tracer import _store_record_sink_outputs


def _valid_evidence(tmp_path, question_id: str = "G0001") -> dict:
    screenshot_files = []
    for section in ("top", "body", "bottom"):
        label = {"top": "01_顶部", "body": "02_正文01", "bottom": "03_底部"}[section]
        path = tmp_path / f"证据_{question_id}_{label}.png"
        path.write_bytes(f"{question_id}-{section}".encode())
        screenshot_files.append(path.name)
    return {
        "id": question_id,
        "question": "孕妇DHA排行榜第一品牌",
        "has_brand": question_id.startswith("B"),
        "status": "completed",
        "chat_url": "https://www.doubao.com/chat/1234567890",
        "answer": "没有官方权威机构发布的排行榜。",
        "collected_at": "2026-08-11T09:00:00Z",
        "page_modules": {
            "keywords": "页面未显示",
            "ref_links": [
                {"title": "孕妇 DHA 选购指南", "url": "https://example.com/dha-guide"}
            ],
            "product_links": "页面未显示",
            "video_links": "页面未显示",
            "followups": ["孕妇补充DHA有哪些注意事项？"],
        },
        "brand_observation": {
            "target": "高吉星",
            "appeared": False,
            "positions": [],
            "natural_recommendation": False,
            "basis": "页面回答和已显示模块未出现高吉星",
        },
        "page_evidence": {
            "screenshot_files": screenshot_files,
            "share_link": {
                "displayed": True,
                "copy_control_displayed": True,
                "capture_method": "share-copy-control",
                "url": "https://www.doubao.com/thread/fixtureG0001",
            },
            "module_expectations": {
                "keywords": {"displayed": False, "expected_count": 0},
                "ref_links": {"displayed": True, "expected_count": 1},
                "product_links": {"displayed": False, "expected_count": 0},
                "video_links": {"displayed": False, "expected_count": 0},
                "followups": {"displayed": True, "expected_count": 1},
            },
            "screenshot_coverage": {"top": True, "answer": True, "bottom": True},
        },
        "required_missing": [],
    }


def _markdown_entry(record: dict) -> str:
    modules = record["page_modules"]
    observation = record["brand_observation"]
    lines = [
        f"## {record['id']}｜{record['question']}",
        "",
        f"- 原问句：{record['question']}",
        "- 状态：已完成",
        f"- 豆包会话 URL（原文）：{record['chat_url']}",
        f"- 分享复制链接：{record['page_evidence']['share_link']['url']}",
        f"- 采集时间：{record['collected_at']}",
        f"- 回答原文（{len(record['answer'])} 字）：",
        "",
        *[f"> {line}" for line in record["answer"].splitlines()],
        "",
        _module_heading("页面显示的关键词", modules["keywords"]),
        _module_heading("参考资料", modules["ref_links"]),
        _module_heading("产品外链", modules["product_links"]),
        _module_heading("相关视频", modules["video_links"]),
        _module_heading("推荐追问", modules["followups"]),
        f"- 高吉星是否出现：{'是' if observation['appeared'] else '否'}",
        "- 高吉星出现位置："
        + (
            "页面未出现"
            if not observation["positions"]
            else "、".join(map(str, observation["positions"]))
        ),
        "- 自然推荐结论："
        + (
            "不适用（品牌词问句）"
            if observation["natural_recommendation"] is None
            else ("是" if observation["natural_recommendation"] else "否")
        )
        + f"（依据：{observation['basis']}）",
        *[
            f"- 原始证据截图：`{filename}`"
            for filename in record["page_evidence"]["screenshot_files"]
        ],
    ]
    for key, label in (
        ("ref_links", "参考资料"),
        ("product_links", "产品外链"),
        ("video_links", "相关视频"),
        ("followups", "推荐追问"),
    ):
        value = modules[key]
        if isinstance(value, list):
            heading_index = lines.index(_module_heading(label, value))
            rendered = [
                f"  {index}. {json.dumps(item, ensure_ascii=False, sort_keys=True)}"
                for index, item in enumerate(value, 1)
            ]
            lines[heading_index + 1 : heading_index + 1] = rendered
    return "\n".join(lines) + "\n"


def _module_heading(label: str, value) -> str:
    if value == "页面未显示":
        return f"- {label}：页面未显示"
    return f"- {label}（{len(value)} 项，按页面顺序）："


def _with_batch_snapshot(
    batch: dict,
    question_items: list[dict] | None = None,
) -> dict:
    items = question_items or [
        {
            "id": question_id,
            "question": f"question:{question_id}",
            "has_brand": question_id.startswith("B"),
        }
        for question_id in batch.get("acceptedQuestionIds", [])
    ]
    snapshot, digest, batch_id = build_gaojixing_batch_snapshot(items)
    return {
        **batch,
        "batchId": batch_id,
        "snapshot": snapshot,
        "snapshotDigest": digest,
    }


@pytest.mark.asyncio
async def test_registered_fixture_batch_accepts_both_phases_after_policy_audit():
    result = await execute_gaojixing_doubao_batch(
        [],
        {
            "sourceMode": "offline_fixture",
            "fixtureId": "gaojixing-doubao-offline-v1",
            "policyVersion": "2.2",
            "phase1Expected": 99,
            "phase2Expected": 88,
        },
    )

    assert result["schema"] == "gaojixing.doubao-batch-result.v1"
    assert result["status"] == "completed"
    assert result["searchTriggered"] is False
    assert result["acceptedQuestionIds"] == ["G0001", "B001"]
    assert result["phaseCounts"] == {"stage1_non_brand": 1, "stage2_brand": 1}
    assert result["recordCount"] == 2
    assert result["snapshot"] == {
        "schema": "gaojixing.question-batch-snapshot.v1",
        "questions": [
            {
                "id": "G0001",
                "question": "孕妇DHA排行榜第一品牌",
                "phase": "stage1_non_brand",
            },
            {
                "id": "B001",
                "question": "高吉星DHA和爱乐维DHA哪个好？",
                "phase": "stage2_brand",
            },
        ],
        "phaseCounts": {"stage1_non_brand": 1, "stage2_brand": 1},
        "recordCount": 2,
    }
    assert re.fullmatch(r"[0-9a-f]{64}", result["snapshotDigest"])
    assert result["batchId"] == f"gaojixing-{result['snapshotDigest']}"
    assert result["audits"] == [
        {"questionId": "G0001", "policyVersion": "2.2", "status": "passed", "violations": []},
        {"questionId": "B001", "policyVersion": "2.2", "status": "passed", "violations": []},
    ]


@pytest.mark.asyncio
async def test_batch_id_is_stable_for_same_question_package_and_changes_with_content(
    tmp_path,
):
    first_evidence = _valid_evidence(tmp_path, "G0001")
    first = await execute_gaojixing_doubao_batch(
        [{"raw": first_evidence}],
        {"sourceMode": "offline_fixture", "projectRoot": str(tmp_path)},
    )
    repeated = await execute_gaojixing_doubao_batch(
        [{"raw": first_evidence}],
        {"sourceMode": "offline_fixture", "projectRoot": str(tmp_path)},
    )
    changed = await execute_gaojixing_doubao_batch(
        [{"raw": {**first_evidence, "question": "孕妇DHA怎么选？"}}],
        {"sourceMode": "offline_fixture", "projectRoot": str(tmp_path)},
    )

    assert repeated["batchId"] == first["batchId"]
    assert repeated["snapshotDigest"] == first["snapshotDigest"]
    assert changed["batchId"] != first["batchId"]
    assert changed["snapshotDigest"] != first["snapshotDigest"]
    assert first["snapshot"]["questions"] == [
        {
            "id": "G0001",
            "question": "孕妇DHA排行榜第一品牌",
            "phase": "stage1_non_brand",
        }
    ]


@pytest.mark.asyncio
async def test_project_archive_rejects_a_question_bank_outside_project_root(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside_bank = tmp_path / "outside.json"
    outside_bank.write_text('{"phase1": [], "phase2": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="question_bank_path_outside_project_root"):
        await execute_gaojixing_doubao_batch(
            [],
            {
                "sourceMode": "project_archive",
                "projectRoot": str(project_root),
                "questionBankPath": str(outside_bank),
            },
        )


@pytest.mark.asyncio
async def test_project_archive_rejects_an_empty_question_batch(tmp_path):
    (tmp_path / "raw").mkdir()
    question_bank = tmp_path / "题库.json"
    question_bank.write_text('{"phase1": [], "phase2": []}', encoding="utf-8")

    result = await execute_gaojixing_doubao_batch(
        [],
        {
            "sourceMode": "project_archive",
            "projectRoot": str(tmp_path),
            "questionBankPath": str(question_bank),
        },
    )

    assert result["status"] == "failed"
    assert result["recordCount"] == 0
    assert "empty_question_batch" in result["batchViolations"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question_bank_document", "violation"),
    [
        (
            {"phase1": {}, "phase2": []},
            "question_bank_phase_not_list:phase1",
        ),
        (
            {"phase1": [None], "phase2": []},
            "question_bank_row_not_object:phase1:0",
        ),
        (
            {"phase1": [{"question": "孕妇DHA怎么选？"}], "phase2": []},
            "question_bank_row_id_invalid:phase1:0",
        ),
        (
            {"phase1": [{"id": "G0001"}], "phase2": []},
            "question_bank_row_question_invalid:phase1:0",
        ),
    ],
)
async def test_malformed_question_bank_blocks_batch_and_certification(
    tmp_path, question_bank_document, violation
):
    (tmp_path / "raw").mkdir()
    question_bank = tmp_path / "题库.json"
    question_bank.write_text(
        json.dumps(question_bank_document, ensure_ascii=False),
        encoding="utf-8",
    )
    params = {
        "sourceMode": "project_archive",
        "projectRoot": str(tmp_path),
        "questionBankPath": str(question_bank),
    }

    batch = await execute_gaojixing_doubao_batch([], params)
    certification = await execute_gaojixing_batch_certification([], params)

    assert batch["status"] == "failed"
    assert violation in batch["batchViolations"]
    assert certification["status"] == "rejected"
    assert violation in certification["violations"]


@pytest.mark.asyncio
async def test_certification_uses_the_upstream_snapshot_instead_of_fixed_phase_inputs():
    batch = await execute_gaojixing_doubao_batch(
        [],
        {
            "sourceMode": "offline_fixture",
            "fixtureId": "gaojixing-doubao-offline-v1",
        },
    )

    result = await execute_gaojixing_batch_certification(
        [{"raw": batch}],
        {
            "sourceMode": "offline_fixture",
            "fixtureId": "gaojixing-doubao-offline-v1",
            "phase1Expected": 99,
            "phase2Expected": 88,
        },
    )

    assert result["status"] == "certified"
    assert result["counts"] == {
        "stage1_non_brand": 1,
        "stage2_brand": 1,
        "total": 2,
    }
    assert result["batchId"] == batch["batchId"]
    assert result["snapshotDigest"] == batch["snapshotDigest"]


@pytest.mark.asyncio
async def test_live_driver_preflight_never_submits_a_question():
    class ReadyDriver:
        async def preflight(self):
            return {
                "status": "ready",
                "binding": "hermes-doubao",
                "checks": {"driver": True, "session": True},
            }

        async def capture(self, _question):
            raise AssertionError("preflight must not submit a Doubao question")

    result = await execute_gaojixing_doubao_batch(
        [],
        {"sourceMode": "live_preflight", "policyVersion": "2.2"},
        driver=ReadyDriver(),
    )

    assert result == {
        "schema": "gaojixing.doubao-driver-preflight.v1",
        "status": "ready",
        "binding": "hermes-doubao",
        "checks": {"driver": True, "session": True},
        "searchTriggered": False,
    }


@pytest.mark.asyncio
async def test_live_preflight_checks_configured_driver_archive_and_pause_marker(
    tmp_path, monkeypatch
):
    driver_path = tmp_path / "gjx_driver.py"
    driver_path.write_text("# preflight only\n", encoding="utf-8")
    question_bank = tmp_path / "题库.json"
    question_bank.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GAOJIXING_HERMES_SESSION_REF", "hermes-session-1")

    ready = await execute_gaojixing_doubao_batch(
        [],
        {
            "sourceMode": "live_preflight",
            "driverPath": str(driver_path),
            "projectRoot": str(tmp_path),
            "questionBankPath": str(question_bank),
        },
    )

    assert ready["status"] == "ready"
    assert ready["checks"] == {
        "driver": True,
        "session": True,
        "projectRoot": True,
        "questionBank": True,
        "notPaused": True,
    }
    assert ready["searchTriggered"] is False

    (tmp_path / ".PAUSED").write_text("verification", encoding="utf-8")
    paused = await execute_gaojixing_doubao_batch(
        [],
        {
            "sourceMode": "live_preflight",
            "driverPath": str(driver_path),
            "projectRoot": str(tmp_path),
            "questionBankPath": str(question_bank),
        },
    )

    assert paused["status"] == "blocked"
    assert paused["checks"]["notPaused"] is False
    assert paused["searchTriggered"] is False


@pytest.mark.asyncio
async def test_visible_captcha_returns_recovery_case_and_uses_configured_feishu(
    tmp_path, monkeypatch
):
    screenshot = tmp_path / "G0002-captcha.png"
    screenshot.write_bytes(b"visible captcha")
    monkeypatch.setenv("TEST_GJX_FEISHU_WEBHOOK", "https://open.feishu.cn/test-hook")

    class RecordingNotifier:
        def __init__(self):
            self.payload = None

        async def send(self, config, payload):
            assert config["webhook_url"] == "https://open.feishu.cn/test-hook"
            self.payload = payload
            return True

    notifier = RecordingNotifier()
    result = await execute_gaojixing_doubao_batch(
        [
            {
                "raw": {
                    "id": "G0002",
                    "question": "孕妇什么时候开始补充DHA？",
                    "status": "verification_required",
                    "verification": {
                        "kind": "captcha",
                        "pageMarkerDetected": True,
                        "screenshotPath": str(screenshot),
                    },
                }
            }
        ],
        {
            "sourceMode": "offline_fixture",
            "policyVersion": "2.2",
            "projectRoot": str(tmp_path),
            "feishuWebhookEnv": "TEST_GJX_FEISHU_WEBHOOK",
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
        notifier=notifier,
        notification_permission_granted=True,
    )

    assert result["status"] == "verification_required"
    assert result["searchTriggered"] is False
    assert result["recoveryCase"] == {
        "schema": "workflow.recovery-case.v1",
        "status": "open",
        "kind": "human_verification_required",
        "questionId": "G0002",
        "question": "孕妇什么时候开始补充DHA？",
        "reason": "captcha",
        "checkpoint": {
            "resumeQuestionId": "G0002",
            "batchId": result["batchId"],
            "snapshotDigest": result["snapshotDigest"],
        },
        "evidence": [
            {
                "type": "screenshot",
                "artifactRef": "run-artifact:G0002-captcha.png",
            }
        ],
        "allowedActions": ["restart_same_batch"],
    }
    assert result["notification"] == {
        "configured": True,
        "delivered": True,
        "blockedByPermission": False,
    }
    assert result["blockedByPermission"] is False
    assert notifier.payload.event == "workflow.recovery_case.opened"
    assert notifier.payload.data["questionId"] == "G0002"
    assert notifier.payload.data["url"] == "run-artifact:G0002-captcha.png"
    assert str(tmp_path) not in json.dumps(result, ensure_ascii=False)
    assert str(tmp_path) not in json.dumps(notifier.payload.data, ensure_ascii=False)


@pytest.mark.asyncio
async def test_visible_captcha_does_not_notify_without_workflow_permission(
    tmp_path, monkeypatch
):
    screenshot = tmp_path / "G0002-captcha.png"
    screenshot.write_bytes(b"visible captcha")
    monkeypatch.setenv("TEST_GJX_FEISHU_WEBHOOK", "https://open.feishu.cn/test-hook")

    class RecordingNotifier:
        def __init__(self):
            self.calls = 0

        async def send(self, config, payload):
            self.calls += 1
            return True

    notifier = RecordingNotifier()
    result = await execute_gaojixing_doubao_batch(
        [
            {
                "raw": {
                    "id": "G0002",
                    "question": "孕妇什么时候开始补充DHA？",
                    "status": "verification_required",
                    "verification": {
                        "kind": "captcha",
                        "pageMarkerDetected": True,
                        "screenshotPath": str(screenshot),
                    },
                }
            }
        ],
        {
            "sourceMode": "offline_fixture",
            "projectRoot": str(tmp_path),
            "feishuWebhookEnv": "TEST_GJX_FEISHU_WEBHOOK",
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
        notifier=notifier,
        notification_permission_granted=False,
    )

    assert result["status"] == "verification_required"
    assert result["blockedByPermission"] is True
    assert result["notification"] == {
        "configured": False,
        "delivered": False,
        "blockedByPermission": True,
    }
    assert notifier.calls == 0


@pytest.mark.asyncio
async def test_verification_screenshot_outside_project_root_never_creates_or_sends_recovery(
    tmp_path, monkeypatch
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    screenshot = tmp_path / "outside-captcha.png"
    screenshot.write_bytes(b"visible captcha")
    monkeypatch.setenv("TEST_GJX_FEISHU_WEBHOOK", "https://open.feishu.cn/test-hook")

    class RecordingNotifier:
        def __init__(self):
            self.calls = 0

        async def send(self, config, payload):
            self.calls += 1
            return True

    notifier = RecordingNotifier()
    result = await execute_gaojixing_doubao_batch(
        [
            {
                "raw": {
                    "id": "G0002",
                    "question": "孕妇什么时候开始补充DHA？",
                    "status": "verification_required",
                    "verification": {
                        "kind": "captcha",
                        "pageMarkerDetected": True,
                        "screenshotPath": str(screenshot),
                    },
                }
            }
        ],
        {
            "sourceMode": "offline_fixture",
            "projectRoot": str(project_root),
            "feishuWebhookEnv": "TEST_GJX_FEISHU_WEBHOOK",
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
        notifier=notifier,
        notification_permission_granted=True,
    )

    assert result["status"] == "failed"
    assert "recoveryCase" not in result
    assert notifier.calls == 0


@pytest.mark.asyncio
async def test_certification_rejects_forged_completed_batch_with_empty_audits():
    result = await execute_gaojixing_batch_certification(
        [
            {
                "raw": _with_batch_snapshot({
                    "schema": "gaojixing.doubao-batch-result.v1",
                    "status": "completed",
                    "recordCount": 2,
                    "acceptedQuestionIds": ["G0001", "B001"],
                    "phaseCounts": {"stage1_non_brand": 1, "stage2_brand": 1},
                    "audits": [],
                    "batchViolations": [],
                    "searchTriggered": False,
                })
            }
        ],
        {
            "sourceMode": "offline_fixture",
            "fixtureId": "gaojixing-doubao-offline-v1",
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "rejected"
    assert "upstream_audit_count_mismatch" in result["violations"]


@pytest.mark.asyncio
async def test_certification_rejects_self_reported_passes_without_evidence():
    batch = _with_batch_snapshot({
        "schema": "gaojixing.doubao-batch-result.v1",
        "status": "completed",
        "recordCount": 2,
        "acceptedQuestionIds": ["G0001", "B001"],
        "phaseCounts": {"stage1_non_brand": 1, "stage2_brand": 1},
        "audits": [
            {"questionId": "G0001", "status": "passed", "violations": []},
            {"questionId": "B001", "status": "passed", "violations": []},
        ],
        "batchViolations": [],
        "searchTriggered": False,
    })

    result = await execute_gaojixing_batch_certification(
        [{"raw": batch}],
        {
            "sourceMode": "offline_fixture",
            "fixtureId": "gaojixing-doubao-offline-v1",
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "rejected"
    assert "upstream_evidence_missing" in result["violations"]


@pytest.mark.asyncio
async def test_certification_reaudits_evidence_instead_of_trusting_passed_audits(
    tmp_path,
):
    stage1 = _valid_evidence(tmp_path, "G0001")
    stage2 = _valid_evidence(tmp_path, "B001")
    stage1["answer"] = ""
    batch = _with_batch_snapshot({
        "schema": "gaojixing.doubao-batch-result.v1",
        "status": "completed",
        "recordCount": 2,
        "acceptedQuestionIds": ["G0001", "B001"],
        "phaseCounts": {"stage1_non_brand": 1, "stage2_brand": 1},
        "audits": [
            {"questionId": "G0001", "status": "passed", "violations": []},
            {"questionId": "B001", "status": "passed", "violations": []},
        ],
        "batchViolations": [],
        "searchTriggered": False,
        "evidence": [stage1, stage2],
        "evidenceRoot": str(tmp_path),
    }, [stage1, stage2])

    result = await execute_gaojixing_batch_certification(
        [{"raw": batch}],
        {
            "sourceMode": "offline_fixture",
            "projectRoot": str(tmp_path),
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "rejected"
    assert (
        "upstream_evidence_audit_failed:G0001:full_answer_missing"
        in result["violations"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "violation"),
    [
        ("count", "upstream_evidence_count_mismatch"),
        ("duplicate", "upstream_evidence_question_ids_invalid"),
        ("accepted_mismatch", "upstream_evidence_question_ids_mismatch"),
    ],
)
async def test_certification_requires_evidence_ids_to_match_accepted_ids(
    tmp_path, mutation, violation
):
    stage1 = _valid_evidence(tmp_path, "G0001")
    stage2 = _valid_evidence(tmp_path, "B001")
    evidence = [stage1, stage2]
    if mutation == "count":
        evidence = [stage1]
    elif mutation == "duplicate":
        evidence = [stage1, stage1]
    elif mutation == "accepted_mismatch":
        evidence = [stage1, {**stage2, "id": "B999"}]
    batch = _with_batch_snapshot({
        "schema": "gaojixing.doubao-batch-result.v1",
        "status": "completed",
        "recordCount": 2,
        "acceptedQuestionIds": ["G0001", "B001"],
        "phaseCounts": {"stage1_non_brand": 1, "stage2_brand": 1},
        "audits": [
            {"questionId": "G0001", "status": "passed", "violations": []},
            {"questionId": "B001", "status": "passed", "violations": []},
        ],
        "batchViolations": [],
        "searchTriggered": False,
        "evidence": evidence,
        "evidenceRoot": str(tmp_path),
    }, [stage1, stage2])

    result = await execute_gaojixing_batch_certification(
        [{"raw": batch}],
        {
            "sourceMode": "offline_fixture",
            "projectRoot": str(tmp_path),
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "rejected"
    assert violation in result["violations"]


@pytest.mark.asyncio
async def test_certification_rejects_non_governed_question_id_prefixes(tmp_path):
    stage1 = {**_valid_evidence(tmp_path, "G0001"), "id": "X001"}
    stage2 = {**_valid_evidence(tmp_path, "B001"), "id": "Y001"}
    batch = _with_batch_snapshot({
        "schema": "gaojixing.doubao-batch-result.v1",
        "status": "completed",
        "recordCount": 2,
        "acceptedQuestionIds": ["X001", "Y001"],
        "phaseCounts": {"stage1_non_brand": 1, "stage2_brand": 1},
        "audits": [
            {"questionId": "X001", "status": "passed", "violations": []},
            {"questionId": "Y001", "status": "passed", "violations": []},
        ],
        "batchViolations": [],
        "searchTriggered": False,
        "evidence": [stage1, stage2],
        "evidenceRoot": str(tmp_path),
    }, [stage1, stage2])

    result = await execute_gaojixing_batch_certification(
        [{"raw": batch}],
        {
            "sourceMode": "offline_fixture",
            "projectRoot": str(tmp_path),
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "rejected"
    assert "upstream_accepted_question_id_format_invalid" in result["violations"]


@pytest.mark.asyncio
async def test_certification_derives_phase_counts_from_evidence_id_prefixes(tmp_path):
    stage1 = _valid_evidence(tmp_path, "G0001")
    another_stage1 = _valid_evidence(tmp_path, "G0002")
    batch = _with_batch_snapshot({
        "schema": "gaojixing.doubao-batch-result.v1",
        "status": "completed",
        "recordCount": 2,
        "acceptedQuestionIds": ["G0001", "G0002"],
        "phaseCounts": {"stage1_non_brand": 1, "stage2_brand": 1},
        "audits": [
            {"questionId": "G0001", "status": "passed", "violations": []},
            {"questionId": "G0002", "status": "passed", "violations": []},
        ],
        "batchViolations": [],
        "searchTriggered": False,
        "evidence": [stage1, another_stage1],
        "evidenceRoot": str(tmp_path),
    }, [stage1, another_stage1])

    result = await execute_gaojixing_batch_certification(
        [{"raw": batch}],
        {
            "sourceMode": "offline_fixture",
            "projectRoot": str(tmp_path),
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "rejected"
    assert "upstream_phase_counts_evidence_mismatch" in result["violations"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "violation"),
    [
        ("schema", "upstream_batch_result_missing"),
        ("record_count", "upstream_record_count_mismatch"),
        ("accepted_duplicate", "upstream_accepted_question_ids_invalid"),
        ("audit_duplicate", "upstream_audit_question_ids_invalid"),
        ("audit_mismatch", "upstream_audit_question_ids_mismatch"),
        ("batch_violations", "upstream_batch_violations_present"),
        ("search_triggered", "upstream_search_triggered_not_false"),
    ],
)
async def test_certification_rejects_each_forged_upstream_contract_field(
    mutation, violation
):
    batch = _with_batch_snapshot({
        "schema": "gaojixing.doubao-batch-result.v1",
        "status": "completed",
        "recordCount": 2,
        "acceptedQuestionIds": ["G0001", "B001"],
        "phaseCounts": {"stage1_non_brand": 1, "stage2_brand": 1},
        "audits": [
            {"questionId": "G0001", "status": "passed", "violations": []},
            {"questionId": "B001", "status": "passed", "violations": []},
        ],
        "batchViolations": [],
        "searchTriggered": False,
    })
    if mutation == "schema":
        batch["schema"] = "forged.schema.v1"
    elif mutation == "record_count":
        batch["recordCount"] = 1
    elif mutation == "accepted_duplicate":
        batch["acceptedQuestionIds"] = ["G0001", "G0001"]
    elif mutation == "audit_duplicate":
        batch["audits"][1]["questionId"] = "G0001"
    elif mutation == "audit_mismatch":
        batch["audits"][1]["questionId"] = "B999"
    elif mutation == "batch_violations":
        batch["batchViolations"] = ["forged"]
    elif mutation == "search_triggered":
        batch["searchTriggered"] = True

    result = await execute_gaojixing_batch_certification(
        [{"raw": batch}],
        {
            "sourceMode": "offline_fixture",
            "fixtureId": "gaojixing-doubao-offline-v1",
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "rejected"
    assert violation in result["violations"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "violation"),
    [
        ("source_mode_missing", "upstream_source_mode_mismatch"),
        ("source_mode_tampered", "upstream_source_mode_mismatch"),
        ("audit_policy_missing", "upstream_audit_policy_version_mismatch"),
        ("audit_policy_tampered", "upstream_audit_policy_version_mismatch"),
    ],
)
async def test_certification_binds_upstream_source_mode_and_audit_policy(
    mutation, violation
):
    batch = await execute_gaojixing_doubao_batch(
        [],
        {
            "sourceMode": "offline_fixture",
            "fixtureId": "gaojixing-doubao-offline-v1",
            "policyVersion": "2.2",
        },
    )
    if mutation == "source_mode_missing":
        batch.pop("sourceMode")
    elif mutation == "source_mode_tampered":
        batch["sourceMode"] = "project_archive"
    elif mutation == "audit_policy_missing":
        batch["audits"][0].pop("policyVersion")
    elif mutation == "audit_policy_tampered":
        batch["audits"][0]["policyVersion"] = "2.1"

    result = await execute_gaojixing_batch_certification(
        [{"raw": batch}],
        {
            "sourceMode": "offline_fixture",
            "fixtureId": "gaojixing-doubao-offline-v1",
            "policyVersion": "2.2",
        },
    )

    assert result["status"] == "rejected"
    assert violation in result["violations"]


@pytest.mark.asyncio
@pytest.mark.parametrize("source_mode", ["live_preflight", "bogus"])
async def test_certification_rejects_non_certification_source_modes(source_mode):
    batch = await execute_gaojixing_doubao_batch(
        [],
        {
            "sourceMode": "offline_fixture",
            "fixtureId": "gaojixing-doubao-offline-v1",
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
    )

    result = await execute_gaojixing_batch_certification(
        [{"raw": batch}],
        {
            "sourceMode": source_mode,
            "fixtureId": "gaojixing-doubao-offline-v1",
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "rejected"
    assert "unsupported_source_mode" in result["violations"]


@pytest.mark.asyncio
async def test_certification_reads_real_v22_project_layout_and_question_bank(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    stage1 = _valid_evidence(tmp_path, "G0001")
    stage2 = _valid_evidence(tmp_path, "B001")
    stage2["question"] = "高吉星DHA和爱乐维DHA哪个好？"
    for record in (stage1, stage2):
        (raw_dir / f"{record['id']}.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )

    (tmp_path / "阶段1_非品牌问句归档.md").write_text(
        _markdown_entry(stage1), encoding="utf-8"
    )
    (tmp_path / "阶段2_品牌问句归档.md").write_text(
        _markdown_entry(stage2), encoding="utf-8"
    )
    (tmp_path / "进度日志.md").write_text(
        "阶段1非品牌题已完成：1 / 1\n阶段2品牌题已完成：1 / 1\n",
        encoding="utf-8",
    )
    (tmp_path / "任务状态.json").write_text(
        json.dumps(
            {
                "completed_count": 2,
                "phase1_complete": True,
                "phase2_complete": True,
                "final_summary": {
                    "phase1": {"total": 1, "completed": 1, "archive_entries": 1},
                    "phase2": {"total": 1, "completed": 1, "archive_entries": 1},
                    "total_raw": 2,
                    "missing_screenshots": 0,
                    "status": "ALL COMPLETE",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    question_bank = tmp_path / "题库.json"
    question_bank.write_text(
        json.dumps(
            {
                "phase1": [{"id": "G0001", "question": stage1["question"]}],
                "phase2": [{"id": "B001", "question": stage2["question"]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await execute_gaojixing_batch_certification(
        [],
        {
            "sourceMode": "project_archive",
            "projectRoot": str(tmp_path),
            "questionBankPath": str(question_bank),
            "phase1Expected": 1,
            "phase2Expected": 1,
            "policyVersion": "2.2",
        },
    )

    evidence_digest = result.pop("evidenceDigest")
    project_records = result.pop("projectRecords")
    batch_id = result.pop("batchId")
    snapshot_digest = result.pop("snapshotDigest")
    snapshot = result.pop("snapshot")
    assert re.fullmatch(r"[0-9a-f]{64}", evidence_digest)
    assert re.fullmatch(r"[0-9a-f]{64}", snapshot_digest)
    assert batch_id == f"gaojixing-{snapshot_digest}"
    assert snapshot["phaseCounts"] == {
        "stage1_non_brand": 1,
        "stage2_brand": 1,
    }
    assert snapshot["recordCount"] == 2
    assert [record["questionId"] for record in project_records] == ["G0001", "B001"]
    assert [record["answer"] for record in project_records] == [
        stage1["answer"],
        stage2["answer"],
    ]
    assert all(
        record["formalChatUrl"] == "https://www.doubao.com/chat/1234567890"
        for record in project_records
    )
    assert all(
        record["shareUrl"].startswith("https://www.doubao.com/thread/")
        for record in project_records
    )
    assert all(record["evidenceDigest"] == evidence_digest for record in project_records)
    assert all(re.fullmatch(r"[0-9a-f]{64}", record["rawDigest"]) for record in project_records)
    assert result == {
        "schema": "gaojixing.batch-certification.v1",
        "status": "certified",
        "policyVersion": "2.2",
        "counts": {"stage1_non_brand": 1, "stage2_brand": 1, "total": 2},
        "violations": [],
        "searchTriggered": False,
        "certificationScope": {
            "kind": "structural-evidence",
            "screenshotChecks": [
                "referenced",
                "exists",
                "insideProjectRoot",
                "sectionPathsDistinct",
                "sha256",
            ],
            "visualContentAuthenticated": False,
            "ocrAuthenticated": False,
        },
    }


    repeated = await execute_gaojixing_batch_certification(
        [],
        {
            "sourceMode": "project_archive",
            "projectRoot": str(tmp_path),
            "questionBankPath": str(question_bank),
            "phase1Expected": 1,
            "phase2Expected": 1,
            "policyVersion": "2.2",
        },
    )
    assert repeated["evidenceDigest"] == evidence_digest

    (tmp_path / stage1["page_evidence"]["screenshot_files"][0]).write_bytes(b"changed")
    changed = await execute_gaojixing_batch_certification(
        [],
        {
            "sourceMode": "project_archive",
            "projectRoot": str(tmp_path),
            "questionBankPath": str(question_bank),
            "phase1Expected": 1,
            "phase2Expected": 1,
            "policyVersion": "2.2",
        },
    )
    assert changed["evidenceDigest"] != evidence_digest


@pytest.mark.asyncio
async def test_certified_gaojixing_projection_materializes_a_managed_project_record(
    db_session,
):
    sink = CompiledWorkflowNode(
        id="delivery",
        kind="sink",
        capability="store",
        params={},
    )
    certification = CompiledWorkflowNode(
        id="certification",
        kind="action",
        capability="accept",
        params={},
    )
    project_record = {
        "schema": "gaojixing.project-record.v1",
        "questionId": "B001",
        "question": "where can the product be purchased",
        "answer": "certified answer",
        "formalChatUrl": "https://www.doubao.com/chat/1234567890",
        "shareUrl": "https://www.doubao.com/thread/B001",
        "rawArtifact": "raw/B001.json",
        "rawDigest": "a" * 64,
        "screenshots": [
            "screenshots/B001/top.png",
            "screenshots/B001/answer.png",
            "screenshots/B001/bottom.png",
        ],
        "evidenceDigest": "b" * 64,
        "batchId": "batch-1",
        "snapshotDigest": "c" * 64,
    }

    stored_refs, skipped = await _store_record_sink_outputs(
        sink,
        [
            {
                "raw": {
                    "schema": "gaojixing.batch-certification.v1",
                    "batchId": "batch-1",
                    "snapshotDigest": "c" * 64,
                    "evidenceDigest": "b" * 64,
                    "projectRecords": [project_record],
                },
                "lineage": [{"nodeId": "certification", "artifact": "certified"}],
            }
        ],
        run_id="run-gaojixing-record",
        workflow_id="workflow-gaojixing",
        target="project-records",
        session=db_session,
        runtime_nodes_by_id={
            sink.id: sink,
            certification.id: certification,
        },
        materialized_source_tasks={},
    )

    assert skipped == 0
    assert len(stored_refs) == 1
    records = (
        await db_session.scalars(
            select(CollectedRecord).where(
                CollectedRecord.workflow_run_id == "run-gaojixing-record"
            )
        )
    ).all()
    assert len(records) == 1
    assert records[0].normalized_data["questionId"] == "B001"
    assert records[0].normalized_data["rawDigest"] == "a" * 64
    source = await db_session.get(DataSource, records[0].source_id)
    task = await db_session.get(CollectionTask, records[0].task_id)
    assert source is not None
    assert source.channel_config["sourceNodeId"] == "gaojixing-certified-archive"
    assert task is not None
    assert task.parameters["workflowRunId"] == "run-gaojixing-record"


@pytest.mark.asyncio
async def test_project_certification_rejects_duplicate_question_bank_ids_and_folded_raw(
    tmp_path,
):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    stage1 = _valid_evidence(tmp_path, "G0001")
    stage2 = _valid_evidence(tmp_path, "B001")
    stage2["question"] = "高吉星DHA和爱乐维DHA哪个好？"
    for record in (stage1, stage2):
        (raw_dir / f"{record['id']}.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
    (tmp_path / "阶段1_非品牌问句归档.md").write_text(
        _markdown_entry(stage1), encoding="utf-8"
    )
    (tmp_path / "阶段2_品牌问句归档.md").write_text(
        _markdown_entry(stage2), encoding="utf-8"
    )
    (tmp_path / "进度日志.md").write_text(
        "阶段1非品牌题已完成：2 / 2\n阶段2品牌题已完成：1 / 1\n",
        encoding="utf-8",
    )
    (tmp_path / "任务状态.json").write_text(
        json.dumps(
            {
                "completed_count": 3,
                "phase1_complete": True,
                "phase2_complete": True,
                "final_summary": {
                    "phase1": {"total": 2, "completed": 2, "archive_entries": 2},
                    "phase2": {"total": 1, "completed": 1, "archive_entries": 1},
                    "total_raw": 3,
                    "status": "ALL COMPLETE",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    question_bank = tmp_path / "题库.json"
    question_bank.write_text(
        json.dumps(
            {
                "phase1": [
                    {"id": "G0001", "question": stage1["question"]},
                    {"id": "G0001", "question": stage1["question"]},
                ],
                "phase2": [{"id": "B001", "question": stage2["question"]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await execute_gaojixing_batch_certification(
        [],
        {
            "sourceMode": "project_archive",
            "projectRoot": str(tmp_path),
            "questionBankPath": str(question_bank),
            "phase1Expected": 2,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "rejected"
    assert "question_bank_duplicate_id:G0001" in result["violations"]
    assert "raw_phase1_count_mismatch" in result["violations"]


@pytest.mark.asyncio
async def test_project_archive_reads_raw_in_question_bank_order_without_search(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    stage1 = _valid_evidence(tmp_path, "G0001")
    stage2 = _valid_evidence(tmp_path, "B001")
    stage2["question"] = "高吉星DHA和爱乐维DHA哪个好？"
    stage2["brand_observation"] = {
        "target": "高吉星",
        "appeared": True,
        "positions": ["回答正文"],
        "natural_recommendation": None,
        "basis": "品牌词问句：只记录出现位置，不判断自然推荐",
    }
    for record in (stage2, stage1):
        (raw_dir / f"{record['id']}.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
    question_bank = tmp_path / "题库.json"
    question_bank.write_text(
        json.dumps(
            {
                "phase1": [{"id": "G0001", "question": stage1["question"]}],
                "phase2": [{"id": "B001", "question": stage2["question"]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await execute_gaojixing_doubao_batch(
        [],
        {
            "sourceMode": "project_archive",
            "projectRoot": str(tmp_path),
            "questionBankPath": str(question_bank),
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "completed"
    assert result["sourceMode"] == "project_archive"
    assert result["searchTriggered"] is False
    assert result["acceptedQuestionIds"] == ["G0001", "B001"]
    assert result["recordCount"] == 2
    assert "evidence" not in result


@pytest.mark.asyncio
async def test_project_archive_rejects_duplicate_question_bank_ids(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    stage1 = _valid_evidence(tmp_path, "G0001")
    stage2 = _valid_evidence(tmp_path, "B001")
    stage2["question"] = "高吉星DHA和爱乐维DHA哪个好？"
    stage2["brand_observation"] = {
        "target": "高吉星",
        "appeared": True,
        "positions": ["回答正文"],
        "natural_recommendation": None,
        "basis": "品牌词问句：只记录出现位置，不判断自然推荐",
    }
    for record in (stage1, stage2):
        (raw_dir / f"{record['id']}.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
    question_bank = tmp_path / "题库.json"
    question_bank.write_text(
        json.dumps(
            {
                "phase1": [
                    {"id": "G0001", "question": stage1["question"]},
                    {"id": "G0001", "question": stage1["question"]},
                ],
                "phase2": [{"id": "B001", "question": stage2["question"]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await execute_gaojixing_doubao_batch(
        [],
        {
            "sourceMode": "project_archive",
            "projectRoot": str(tmp_path),
            "questionBankPath": str(question_bank),
            "phase1Expected": 2,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "failed"
    assert "question_bank_duplicate_id:G0001" in result["batchViolations"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "expected_violation"),
    [
        ("answer", "markdown_answer_mismatch:G0001"),
        ("module", "markdown_module_ref_links_mismatch:G0001"),
        ("brand", "markdown_brand_observation_mismatch:G0001"),
    ],
)
async def test_certification_rejects_raw_markdown_content_drift(
    tmp_path, mutation, expected_violation
):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    stage1 = _valid_evidence(tmp_path, "G0001")
    stage2 = _valid_evidence(tmp_path, "B001")
    stage2["question"] = "高吉星DHA和爱乐维DHA哪个好？"
    for record in (stage1, stage2):
        (raw_dir / f"{record['id']}.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
    stage1_markdown = _markdown_entry(stage1)
    if mutation == "answer":
        stage1_markdown = stage1_markdown.replace(stage1["answer"], "归档回答被改写")
    elif mutation == "module":
        stage1_markdown = stage1_markdown.replace(
            "https://example.com/dha-guide", "https://example.com/wrong"
        )
    else:
        stage1_markdown = stage1_markdown.replace(
            "页面回答和已显示模块未出现高吉星", "归档依据被改写"
        )
    (tmp_path / "阶段1_非品牌问句归档.md").write_text(
        stage1_markdown, encoding="utf-8"
    )
    (tmp_path / "阶段2_品牌问句归档.md").write_text(
        _markdown_entry(stage2), encoding="utf-8"
    )
    (tmp_path / "进度日志.md").write_text(
        "阶段1非品牌题已完成：1 / 1\n阶段2品牌题已完成：1 / 1\n",
        encoding="utf-8",
    )
    (tmp_path / "任务状态.json").write_text(
        json.dumps(
            {
                "completed_count": 2,
                "phase1_complete": True,
                "phase2_complete": True,
                "final_summary": {
                    "phase1": {"total": 1, "completed": 1, "archive_entries": 1},
                    "phase2": {"total": 1, "completed": 1, "archive_entries": 1},
                    "total_raw": 2,
                    "status": "ALL COMPLETE",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    question_bank = tmp_path / "题库.json"
    question_bank.write_text(
        json.dumps(
            {
                "phase1": [{"id": "G0001", "question": stage1["question"]}],
                "phase2": [{"id": "B001", "question": stage2["question"]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await execute_gaojixing_batch_certification(
        [],
        {
            "sourceMode": "project_archive",
            "projectRoot": str(tmp_path),
            "questionBankPath": str(question_bank),
            "phase1Expected": 1,
            "phase2Expected": 1,
        },
    )

    assert result["status"] == "rejected"
    assert expected_violation in result["violations"]


def test_two_gaojixing_packages_materialize_to_real_tools_and_compile():
    stale_interface = {
        "groups": [{"id": "legacy", "label": "Legacy"}],
        "fields": [
            {
                "id": "language",
                "label": "Language",
                "groupId": "legacy",
                "type": "text",
                "binding": {
                    "nodeId": "language",
                    "source": "params",
                    "fieldId": "language",
                },
                "value": "zh-CN",
            }
        ],
    }
    project = WorkflowProject.model_validate(
        {
            "id": "wf-gaojixing-two-hda",
            "name": "Gaojixing two HDA",
            "profile": "intelligence",
            "version": 1,
            "nodes": [
                {
                    "id": "batch",
                    "kind": "agent",
                    "capability": "normalize",
                    "params": {
                        "template": "gaojixing-doubao-batch",
                        "sourceMode": "offline_fixture",
                        "fixtureId": "gaojixing-doubao-offline-v1",
                        "phase1Expected": 1,
                        "phase2Expected": 1,
                        "toolParams": {
                            "sourceMode": "project_archive",
                            "fixtureId": "stale-fixture",
                            "phase1Expected": 446,
                            "phase2Expected": 32,
                        },
                    },
                    "parameterInterface": stale_interface,
                    "ui": {"catalogId": "package.gaojixing.doubao-batch"},
                },
                {
                    "id": "certify",
                    "kind": "agent",
                    "capability": "normalize",
                    "params": {
                        "template": "gaojixing-batch-certification",
                        "sourceMode": "offline_fixture",
                        "fixtureId": "gaojixing-doubao-offline-v1",
                        "phase1Expected": 1,
                        "phase2Expected": 1,
                        "toolParams": {
                            "sourceMode": "project_archive",
                            "fixtureId": "stale-fixture",
                            "phase1Expected": 446,
                            "phase2Expected": 32,
                        },
                    },
                    "parameterInterface": stale_interface,
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
        }
    )

    materialized = materialize_hda_templates(project)
    batch, certify = materialized.nodes

    assert batch.parameterInterface is None
    assert certify.parameterInterface is None
    assert (
        batch.params["toolParams"]["feishuWebhookEnv"]
        == "GAOJIXING_FEISHU_WEBHOOK_URL"
    )
    for package in (batch, certify):
        assert package.params["toolParams"]["sourceMode"] == "offline_fixture"
        assert package.params["toolParams"]["fixtureId"] == "gaojixing-doubao-offline-v1"
        assert "phase1Expected" not in package.params["toolParams"]
        assert "phase2Expected" not in package.params["toolParams"]
    tool_ids = [
        node.params["toolCapability"]["id"]
        for node in (batch.internals.nodes[0], certify.internals.nodes[0])
    ]
    assert tool_ids == [
        "tool.gaojixing.doubao-batch.run",
        "tool.gaojixing.batch-certify",
    ]
    assert len(batch.internals.nodes) == 1
    assert len(certify.internals.nodes) == 1
    compiled = compile_workflow_project(materialized)
    assert compiled.valid is True
    assert compiled.plan is not None
    assert "batch::tool" in compiled.plan.runtime.node_ids
    assert "certify::tool" in compiled.plan.runtime.node_ids


@pytest.mark.parametrize("displayed_count", [1, 16, 30])
def test_reference_count_accepts_the_exact_page_declared_number(tmp_path, displayed_count):
    evidence = _valid_evidence(tmp_path)
    evidence["page_modules"]["ref_links"] = [
        {"title": f"参考资料 {index}", "url": f"https://example.com/reference/{index}"}
        for index in range(1, displayed_count + 1)
    ]
    evidence["page_evidence"]["module_expectations"]["ref_links"] = {
        "displayed": True,
        "expected_count": displayed_count,
    }

    assert audit_gaojixing_question_evidence(evidence, project_root=tmp_path) == []


@pytest.mark.parametrize("displayed_count", [1, 16, 30])
def test_reference_count_rejects_one_missing_link(tmp_path, displayed_count):
    evidence = _valid_evidence(tmp_path)
    evidence["page_modules"]["ref_links"] = [
        {"title": f"参考资料 {index}", "url": f"https://example.com/reference/{index}"}
        for index in range(1, displayed_count)
    ]
    evidence["page_evidence"]["module_expectations"]["ref_links"] = {
        "displayed": True,
        "expected_count": displayed_count,
    }

    assert "module_count_ref_links_mismatch" in audit_gaojixing_question_evidence(
        evidence, project_root=tmp_path
    )


def test_related_video_accepts_absent_or_complete_account_title_and_screenshot(tmp_path):
    absent = _valid_evidence(tmp_path, "G0002")
    assert audit_gaojixing_question_evidence(absent, project_root=tmp_path) == []

    displayed = _valid_evidence(tmp_path, "G0003")
    player = tmp_path / "证据_G0003_相关视频同屏.svg"
    player.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    displayed["page_modules"]["video_links"] = [
        {"account": "营养师小张", "title": "孕期DHA怎么选", "screenshot_file": player.name}
    ]
    displayed["page_evidence"]["module_expectations"]["video_links"] = {
        "displayed": True,
        "expected_count": 1,
    }
    assert audit_gaojixing_question_evidence(displayed, project_root=tmp_path) == []


@pytest.mark.parametrize("missing_key", ["account", "title", "screenshot_file"])
def test_related_video_rejects_any_missing_required_evidence(tmp_path, missing_key):
    evidence = _valid_evidence(tmp_path, "G0004")
    player = tmp_path / "证据_G0004_相关视频同屏.svg"
    player.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    video = {"account": "营养师小张", "title": "孕期DHA怎么选", "screenshot_file": player.name}
    del video[missing_key]
    evidence["page_modules"]["video_links"] = [video]
    evidence["page_evidence"]["module_expectations"]["video_links"] = {
        "displayed": True,
        "expected_count": 1,
    }

    assert "related_video_evidence_incomplete" in audit_gaojixing_question_evidence(
        evidence, project_root=tmp_path
    )


def test_displayed_product_link_must_be_clickable(tmp_path):
    evidence = _valid_evidence(tmp_path, "G0007")
    evidence["page_modules"]["product_links"] = [{"title": "高吉星 DHA"}]
    evidence["page_evidence"]["module_expectations"]["product_links"] = {
        "displayed": True,
        "expected_count": 1,
    }

    assert "product_link_item_incomplete" in audit_gaojixing_question_evidence(
        evidence, project_root=tmp_path
    )


def test_share_link_is_required_when_it_is_not_explicitly_absent_from_the_page(tmp_path):
    evidence = _valid_evidence(tmp_path, "G0007")
    del evidence["page_evidence"]["share_link"]

    assert "share_link_missing" in audit_gaojixing_question_evidence(
        evidence, project_root=tmp_path
    )


def test_share_link_cannot_be_claimed_as_absent_from_a_completed_answer(tmp_path):
    evidence = _valid_evidence(tmp_path, "G0007")
    evidence["page_evidence"]["share_link"] = {
        "displayed": False,
        "copy_control_displayed": False,
        "url": "页面未显示",
    }

    assert "share_link_copy_control_missing" in audit_gaojixing_question_evidence(
        evidence, project_root=tmp_path
    )


def test_share_link_accepts_the_copied_doubao_thread_url(tmp_path):
    evidence = _valid_evidence(tmp_path, "G0008")
    evidence["page_evidence"]["share_link"] = {
        "displayed": True,
        "copy_control_displayed": True,
        "capture_method": "share-copy-control",
        "url": "https://www.doubao.com/thread/xg8AbxCMCtMcDYoUs",
    }

    violations = audit_gaojixing_question_evidence(evidence, project_root=tmp_path)

    assert not [item for item in violations if item.startswith("share_link_")]


def test_share_link_rejects_the_address_bar_conversation_url(tmp_path):
    evidence = _valid_evidence(tmp_path, "G0008")
    evidence["page_evidence"]["share_link"]["url"] = (
        "https://www.doubao.com/chat/38437069588741378"
    )

    assert "share_link_unavailable" in audit_gaojixing_question_evidence(
        evidence, project_root=tmp_path
    )


def test_displayed_module_cannot_claim_zero_or_page_not_displayed(tmp_path):
    evidence = _valid_evidence(tmp_path, "G0008")
    evidence["page_evidence"]["module_expectations"]["ref_links"] = {
        "displayed": True,
        "expected_count": 0,
    }
    evidence["page_modules"]["ref_links"] = "页面未显示"

    violations = audit_gaojixing_question_evidence(evidence, project_root=tmp_path)
    assert "module_ref_links_displayed_content_missing" in violations


def test_absent_recommended_followups_are_an_explicit_optional_module(
    tmp_path,
):
    evidence = _valid_evidence(tmp_path, "G0009")
    evidence["page_modules"]["followups"] = "页面未显示"
    evidence["page_evidence"]["module_expectations"]["followups"] = {
        "displayed": False,
        "expected_count": 0,
    }

    assert audit_gaojixing_question_evidence(evidence, project_root=tmp_path) == []


def test_three_coverage_flags_cannot_be_backed_by_one_screenshot(tmp_path):
    evidence = _valid_evidence(tmp_path, "G0005")
    evidence["page_evidence"]["screenshot_files"] = [
        evidence["page_evidence"]["screenshot_files"][0]
    ]

    assert "screenshot_sections_incomplete" in audit_gaojixing_question_evidence(
        evidence, project_root=tmp_path
    )


def test_absolute_screenshot_outside_project_root_is_rejected(tmp_path):
    evidence = _valid_evidence(tmp_path, "G0009")
    outside = tmp_path.parent / "证据_G0009_01_顶部.png"
    outside.write_bytes(b"outside")
    evidence["page_evidence"]["screenshot_files"][0] = str(outside.resolve())

    assert "screenshot_file_missing" in audit_gaojixing_question_evidence(
        evidence, project_root=tmp_path
    )


def test_evidence_digest_includes_same_basename_from_distinct_directories(tmp_path):
    raw_dir = tmp_path / "raw"
    first_dir = tmp_path / "screenshots" / "first"
    second_dir = tmp_path / "screenshots" / "second"
    raw_dir.mkdir()
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)
    first = first_dir / "证据_G0010_01_顶部.png"
    second = second_dir / "证据_G0010_01_顶部.png"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    (raw_dir / "G0010.json").write_text(
        json.dumps(
            {
                "page_evidence": {
                    "screenshot_files": [
                        "screenshots/first/证据_G0010_01_顶部.png",
                        "screenshots/second/证据_G0010_01_顶部.png",
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    question_bank = tmp_path / "题库.json"
    question_bank.write_text("{}", encoding="utf-8")
    baseline = _evidence_digest(tmp_path, question_bank)

    first.write_bytes(b"first-changed")
    first_changed = _evidence_digest(tmp_path, question_bank)
    first.write_bytes(b"first")
    second.write_bytes(b"second-changed")
    second_changed = _evidence_digest(tmp_path, question_bank)

    assert first_changed != baseline
    assert second_changed != baseline


def test_non_brand_question_requires_a_boolean_natural_recommendation(tmp_path):
    evidence = _valid_evidence(tmp_path, "G0006")
    evidence["brand_observation"]["natural_recommendation"] = None
    evidence["brand_observation"]["basis"] = "不判断自然推荐"

    assert "brand_observation_incomplete" in audit_gaojixing_question_evidence(
        evidence, project_root=tmp_path
    )


@pytest.mark.asyncio
async def test_stage2_cannot_start_before_stage1_has_passed(tmp_path):
    stage2 = _valid_evidence(tmp_path, "B001")
    stage1 = _valid_evidence(tmp_path, "G0001")

    result = await execute_gaojixing_doubao_batch(
        [{"raw": stage2}, {"raw": stage1}],
        {
            "sourceMode": "offline_fixture",
            "projectRoot": str(tmp_path),
            "phase1Expected": 1,
            "phase2Expected": 1,
            "requirePhase1BeforePhase2": True,
        },
    )

    assert result["status"] == "failed"
    assert "phase2_started_before_phase1_complete" in result["batchViolations"]


@pytest.mark.asyncio
async def test_empty_unregistered_fixture_cannot_complete():
    with pytest.raises(ValueError, match="registered_fixture_id_required"):
        await execute_gaojixing_doubao_batch(
            [],
            {
                "sourceMode": "offline_fixture",
                "phase1Expected": 1,
                "phase2Expected": 1,
            },
        )


@pytest.mark.asyncio
async def test_unimplemented_live_search_mode_is_rejected():
    with pytest.raises(ValueError, match="unsupported_gaojixing_source_mode:live"):
        await execute_gaojixing_doubao_batch(
            [],
            {
                "sourceMode": "live",
                "phase1Expected": 1,
                "phase2Expected": 1,
            },
        )
