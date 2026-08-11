"""Deep runtime module for the Gaojixing Doubao evidence batch."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Protocol

from backend.notifiers.base import AbstractNotifier, NotificationPayload
from backend.notifiers.feishu_notifier import FeishuNotifier

GAOJIXING_DOUBAO_BATCH_TOOL_ID = "tool.gaojixing.doubao-batch.run"
GAOJIXING_DOUBAO_BATCH_EXECUTOR = "gaojixing_doubao_batch"
GAOJIXING_POLICY_VERSION = "2.2"
GAOJIXING_FEISHU_WEBHOOK_ENV = "GAOJIXING_FEISHU_WEBHOOK_URL"

_FIXTURE_PATHS = {
    "gaojixing-doubao-offline-v1": (
        Path(__file__).parent / "fixtures" / "gaojixing_doubao_offline.json"
    )
}

_FORMAL_CHAT_URL = re.compile(r"^https://www\.doubao\.com/chat/\d+$")
_PAGE_MODULES = {"keywords", "ref_links", "product_links", "video_links", "followups"}


def resolve_registered_fixture_root(fixture_id: str) -> Path | None:
    """Return the governed root for a registered offline fixture."""

    fixture_path = _FIXTURE_PATHS.get(fixture_id)
    return fixture_path.parent.resolve() if fixture_path is not None else None


class DoubaoDriverPort(Protocol):
    async def preflight(self) -> dict[str, Any]: ...

    async def capture(self, question: dict[str, Any]) -> dict[str, Any]: ...


class HermesDoubaoDriver:
    """Production driver boundary; preflight is guaranteed read-only."""

    def __init__(
        self,
        *,
        driver_path: str = "",
        project_root: str = "",
        question_bank_path: str = "",
    ) -> None:
        self.driver_path = driver_path
        self.project_root = Path(project_root) if project_root else None
        self.question_bank_path = Path(question_bank_path) if question_bank_path else None

    async def preflight(self) -> dict[str, Any]:
        executable = self.driver_path or os.environ.get(
            "GAOJIXING_DOUBAO_DRIVER", "gjx-doubao-driver"
        )
        executable_path = Path(executable)
        driver_ready = executable_path.is_file() or shutil.which(executable) is not None
        session_ready = bool(os.environ.get("GAOJIXING_HERMES_SESSION_REF"))
        project_ready = self.project_root is not None and self.project_root.is_dir()
        question_bank_ready = (
            self.question_bank_path is not None and self.question_bank_path.is_file()
        )
        not_paused = project_ready and not (self.project_root / ".PAUSED").exists()
        checks = {
            "driver": driver_ready,
            "session": session_ready,
            "projectRoot": project_ready,
            "questionBank": question_bank_ready,
            "notPaused": not_paused,
        }
        return {
            "status": "ready" if all(checks.values()) else "blocked",
            "binding": "hermes-doubao",
            "checks": checks,
        }

    async def capture(self, question: dict[str, Any]) -> dict[str, Any]:
        del question
        raise RuntimeError("live_capture_requires_certified_driver_binding")


async def execute_gaojixing_doubao_batch(
    input_items: list[dict[str, Any]],
    params: dict[str, Any],
    *,
    driver: DoubaoDriverPort | None = None,
    notifier: AbstractNotifier | None = None,
    notification_permission_granted: bool = False,
) -> dict[str, Any]:
    """Execute one governed batch without exposing its per-question graph.

    Offline fixtures and an existing project archive are executable. The only
    live mode is a non-mutating driver preflight; this capability never submits
    a Doubao question.
    """

    source_mode = str(params.get("sourceMode") or "offline_fixture")
    policy_version = str(params.get("policyVersion") or GAOJIXING_POLICY_VERSION)
    if source_mode == "live_preflight":
        readiness = await (
            driver
            or HermesDoubaoDriver(
                driver_path=str(params.get("driverPath") or ""),
                project_root=str(params.get("projectRoot") or ""),
                question_bank_path=str(params.get("questionBankPath") or ""),
            )
        ).preflight()
        return {
            "schema": "gaojixing.doubao-driver-preflight.v1",
            **readiness,
            "searchTriggered": False,
        }
    phase1_expected = _positive_expected_count(params, "phase1Expected")
    phase2_expected = _positive_expected_count(params, "phase2Expected")
    if source_mode == "offline_fixture":
        captures, fixture_root = _resolve_fixture_captures(input_items, params)
        project_root = Path(str(params.get("projectRoot") or fixture_root))
        source_violations: list[str] = []
    elif source_mode == "project_archive":
        captures, project_root, source_violations = _resolve_project_archive_captures(
            params,
            phase1_expected=phase1_expected,
            phase2_expected=phase2_expected,
        )
    else:
        raise ValueError(f"unsupported_gaojixing_source_mode:{source_mode}")

    audits: list[dict[str, Any]] = []
    accepted_ids: list[str] = []
    phase_counts = {"stage1_non_brand": 0, "stage2_brand": 0}
    batch_violations = list(source_violations)
    for capture in captures:
        recovery_case = _visible_verification_recovery_case(
            capture,
            project_root=project_root,
        )
        if recovery_case is not None:
            notification = await _notify_recovery_case(
                recovery_case,
                feishu_webhook_env=str(params.get("feishuWebhookEnv") or ""),
                notifier=notifier,
                notification_permission_granted=notification_permission_granted,
            )
            return {
                "schema": "gaojixing.doubao-batch-result.v1",
                "status": "verification_required",
                "sourceMode": source_mode,
                "searchTriggered": False,
                "acceptedQuestionIds": accepted_ids,
                "phaseCounts": phase_counts,
                "audits": audits,
                "recoveryCase": recovery_case,
                "notification": notification,
                "blockedByPermission": notification["blockedByPermission"],
            }
        question_id = str(capture.get("id") or "")
        phase = _question_phase(capture)
        if (
            phase == "stage2_brand"
            and params.get("requirePhase1BeforePhase2") is not False
            and phase_counts["stage1_non_brand"] != phase1_expected
        ):
            violation = "phase2_started_before_phase1_complete"
            batch_violations.append(violation)
            audits.append(
                {
                    "questionId": question_id,
                    "policyVersion": policy_version,
                    "status": "rejected",
                    "violations": [violation],
                }
            )
            continue
        violations = audit_gaojixing_question_evidence(capture, project_root=project_root)
        audits.append(
            {
                "questionId": question_id,
                "policyVersion": policy_version,
                "status": "passed" if not violations else "rejected",
                "violations": violations,
            }
        )
        if violations:
            continue
        accepted_ids.append(question_id)
        phase_counts[phase] += 1

    if phase_counts["stage1_non_brand"] != phase1_expected:
        batch_violations.append("phase1_count_mismatch")
    if phase_counts["stage2_brand"] != phase2_expected:
        batch_violations.append("phase2_count_mismatch")
    result = {
        "schema": "gaojixing.doubao-batch-result.v1",
        "status": (
            "completed"
            if len(accepted_ids) == len(captures) and not batch_violations
            else "failed"
        ),
        "sourceMode": source_mode,
        "searchTriggered": False,
        "acceptedQuestionIds": accepted_ids,
        "phaseCounts": phase_counts,
        "audits": audits,
        "batchViolations": sorted(set(batch_violations)),
        "recordCount": len(captures),
    }
    if source_mode == "offline_fixture":
        result["evidence"] = captures
        result["evidenceRoot"] = str(project_root.resolve())
        fixture_id = str(params.get("fixtureId") or "").strip()
        if fixture_id:
            result["fixtureId"] = fixture_id
    return result


def _resolve_fixture_captures(
    input_items: list[dict[str, Any]],
    params: dict[str, Any],
) -> tuple[list[dict[str, Any]], Path]:
    captures = []
    for item in input_items:
        capture = item.get("raw") if isinstance(item.get("raw"), dict) else item
        if isinstance(capture, dict):
            captures.append(capture)
    if captures:
        return captures, Path(str(params.get("projectRoot") or "."))

    fixture_id = str(params.get("fixtureId") or "")
    fixture_path = _FIXTURE_PATHS.get(fixture_id)
    if fixture_path is None:
        raise ValueError("registered_fixture_id_required")
    document = json.loads(fixture_path.read_text(encoding="utf-8"))
    records = document.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("registered_fixture_has_no_records")
    return [record for record in records if isinstance(record, dict)], fixture_path.parent


def _resolve_project_archive_captures(
    params: dict[str, Any],
    *,
    phase1_expected: int,
    phase2_expected: int,
) -> tuple[list[dict[str, Any]], Path, list[str]]:
    project_root = Path(str(params.get("projectRoot") or ""))
    question_bank_path = Path(str(params.get("questionBankPath") or ""))
    if not project_root.is_dir():
        raise ValueError("project_root_missing")
    try:
        question_bank = json.loads(question_bank_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("question_bank_unreadable") from exc
    if not isinstance(question_bank, dict):
        raise ValueError("question_bank_invalid")

    phase_rows = {
        phase: _project_question_rows(question_bank.get(phase))
        for phase in ("phase1", "phase2")
    }
    violations: list[str] = []
    all_rows = [*phase_rows["phase1"], *phase_rows["phase2"]]
    question_id_counts: dict[str, int] = {}
    for row in all_rows:
        question_id = row["id"]
        question_id_counts[question_id] = question_id_counts.get(question_id, 0) + 1
    violations.extend(
        f"question_bank_duplicate_id:{question_id}"
        for question_id, count in sorted(question_id_counts.items())
        if count > 1
    )
    if len(phase_rows["phase1"]) != phase1_expected:
        violations.append("question_bank_phase1_count_mismatch")
    if len(phase_rows["phase2"]) != phase2_expected:
        violations.append("question_bank_phase2_count_mismatch")

    raw_dir = project_root / "raw"
    raw_paths = {path.stem: path for path in raw_dir.glob("*.json")} if raw_dir.is_dir() else {}
    expected_ids = {row["id"] for row in all_rows}
    violations.extend(
        f"raw_unexpected:{question_id}"
        for question_id in sorted(set(raw_paths) - expected_ids)
    )
    captures: list[dict[str, Any]] = []
    for row in all_rows:
        question_id = row["id"]
        raw_path = raw_paths.get(question_id)
        if raw_path is None:
            violations.append(f"raw_missing:{question_id}")
            continue
        try:
            record = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            violations.append(f"raw_unreadable:{question_id}")
            continue
        if not isinstance(record, dict):
            violations.append(f"raw_invalid:{question_id}")
            continue
        if record.get("id") != question_id:
            violations.append(f"raw_id_mismatch:{question_id}")
        if record.get("question") != row["question"]:
            violations.append(f"original_question_mismatch:{question_id}")
        captures.append(record)
    return captures, project_root, violations


def _project_question_rows(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    return [
        {"id": str(row["id"]), "question": str(row["question"])}
        for row in value
        if isinstance(row, dict) and row.get("id") and row.get("question")
    ]


def _positive_expected_count(params: dict[str, Any], name: str) -> int:
    value = params.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name}_must_be_positive")
    return value


def _visible_verification_recovery_case(
    capture: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any] | None:
    verification = capture.get("verification")
    if (
        capture.get("status") != "verification_required"
        or not isinstance(verification, dict)
        or verification.get("pageMarkerDetected") is not True
        or verification.get("kind") not in {"captcha", "login", "access"}
    ):
        return None
    screenshot_path = str(verification.get("screenshotPath") or "")
    resolved_screenshot = _resolve_project_artifact(project_root, screenshot_path)
    if resolved_screenshot is None:
        return None
    question_id = str(capture.get("id") or capture.get("questionId") or "")
    question = str(capture.get("question") or capture.get("originalQuestion") or "")
    return {
        "schema": "workflow.recovery-case.v1",
        "status": "open",
        "kind": "human_verification_required",
        "questionId": question_id,
        "question": question,
        "reason": verification["kind"],
        "checkpoint": {"resumeQuestionId": question_id},
        "evidence": [{"type": "screenshot", "path": str(resolved_screenshot)}],
        "allowedActions": ["resume_same_question"],
    }


async def _notify_recovery_case(
    recovery_case: dict[str, Any],
    *,
    feishu_webhook_env: str,
    notifier: AbstractNotifier | None,
    notification_permission_granted: bool,
) -> dict[str, bool]:
    if not notification_permission_granted:
        return {
            "configured": False,
            "delivered": False,
            "blockedByPermission": True,
        }
    webhook_url = os.environ.get(feishu_webhook_env, "") if feishu_webhook_env else ""
    if not webhook_url:
        return {
            "configured": False,
            "delivered": False,
            "blockedByPermission": False,
        }
    payload = NotificationPayload(
        event="workflow.recovery_case.opened",
        source_id="gaojixing-doubao-batch",
        data={
            "title": "高吉星豆包搜索需人工验证",
            "summary": recovery_case["reason"],
            "questionId": recovery_case["questionId"],
            "question": recovery_case["question"],
            "url": recovery_case["evidence"][0]["path"],
        },
    )
    delivered = bool(
        await (notifier or FeishuNotifier()).send(
            {
                "webhook_url": webhook_url,
                "title": "【高吉星豆包搜索需人工验证】{{questionId}}",
                "content": (
                    "题号：{{questionId}}\n原问句：{{question}}\n"
                    "页面异常：{{summary}}\n证据截图：{{url}}\n"
                    "处理后请回复：验证完成，继续"
                ),
            },
            payload,
        )
    )
    return {
        "configured": True,
        "delivered": delivered,
        "blockedByPermission": False,
    }


def _question_phase(evidence: dict[str, Any]) -> str:
    return (
        "stage2_brand"
        if str(evidence.get("id") or "").startswith("B") or evidence.get("has_brand") is True
        else "stage1_non_brand"
    )


def audit_gaojixing_question_evidence(
    evidence: dict[str, Any],
    *,
    project_root: Path,
) -> list[str]:
    violations: list[str] = []
    if not re.fullmatch(r"(?:G\d{4}|B\d{3})", str(evidence.get("id") or "")):
        violations.append("question_id_missing")
    if not str(evidence.get("question") or "").strip():
        violations.append("original_question_missing")
    if evidence.get("status") != "completed":
        violations.append("status_not_completed")
    if not _FORMAL_CHAT_URL.fullmatch(str(evidence.get("chat_url") or "")):
        violations.append("formal_chat_url_invalid")
    if not str(evidence.get("answer") or "").strip():
        violations.append("full_answer_missing")
    if not str(evidence.get("collected_at") or "").strip():
        violations.append("collected_at_missing")

    page_modules = evidence.get("page_modules")
    if not isinstance(page_modules, dict) or set(page_modules) != _PAGE_MODULES:
        violations.append("page_modules_incomplete")
    elif any(not _module_has_explicit_value(page_modules[name]) for name in _PAGE_MODULES):
        violations.append("page_module_content_missing")

    page_evidence = evidence.get("page_evidence")
    if not isinstance(page_evidence, dict):
        violations.append("page_evidence_missing")
    else:
        expectations = page_evidence.get("module_expectations")
        if not isinstance(expectations, dict) or set(expectations) != _PAGE_MODULES:
            violations.append("module_expectations_incomplete")
        elif isinstance(page_modules, dict):
            violations.extend(_audit_module_counts(page_modules, expectations, project_root))
        screenshot_files = page_evidence.get("screenshot_files")
        if not isinstance(screenshot_files, list) or not screenshot_files:
            violations.append("screenshots_missing")
        else:
            if any(
                not _artifact_exists(project_root, str(filename))
                for filename in screenshot_files
            ):
                violations.append("screenshot_file_missing")
            if not _screenshot_sections_complete(screenshot_files):
                violations.append("screenshot_sections_incomplete")
        coverage = page_evidence.get("screenshot_coverage")
        if not isinstance(coverage, dict) or any(
            coverage.get(name) is not True for name in ("top", "answer", "bottom")
        ):
            violations.append("screenshot_coverage_incomplete")

    observation = evidence.get("brand_observation")
    if not _brand_observation_complete(evidence, observation):
        violations.append("brand_observation_incomplete")
    if evidence.get("required_missing") != []:
        violations.append("required_fields_missing")
    return violations


def _module_has_explicit_value(value: Any) -> bool:
    return value == "页面未显示" or (isinstance(value, list) and bool(value))


def _audit_module_counts(
    modules: dict[str, Any],
    expectations: dict[str, Any],
    project_root: Path,
) -> list[str]:
    violations: list[str] = []
    for name in _PAGE_MODULES:
        expectation = expectations.get(name)
        if not isinstance(expectation, dict) or not isinstance(expectation.get("displayed"), bool):
            violations.append(f"module_expectation_{name}_invalid")
            continue
        expected_count = expectation.get("expected_count")
        if not isinstance(expected_count, int) or isinstance(expected_count, bool):
            violations.append(f"module_expectation_{name}_invalid")
            continue
        value = modules[name]
        actual_count = len(value) if isinstance(value, list) else 0
        if actual_count != expected_count:
            violations.append(f"module_count_{name}_mismatch")
        if expectation["displayed"] is True and (
            not isinstance(value, list) or not value or expected_count <= 0
        ):
            violations.append(f"module_{name}_displayed_content_missing")
        if expectation["displayed"] is False and value != "页面未显示":
            violations.append(f"module_{name}_absence_not_explicit")

    references = modules.get("ref_links")
    if isinstance(references, list) and any(
        not isinstance(item, dict)
        or not str(item.get("title") or "").strip()
        or not str(item.get("url") or "").startswith(("http://", "https://"))
        for item in references
    ):
        violations.append("reference_item_incomplete")

    products = modules.get("product_links")
    if isinstance(products, list) and any(
        not isinstance(item, dict)
        or not str(item.get("title") or item.get("name") or item.get("text") or "").strip()
        or not str(item.get("url") or item.get("href") or "").startswith(
            ("http://", "https://")
        )
        for item in products
    ):
        violations.append("product_link_item_incomplete")

    for name in ("keywords", "followups"):
        items = modules.get(name)
        if isinstance(items, list) and any(
            not str(
                item.get("text") or item.get("title") or ""
                if isinstance(item, dict)
                else item
            ).strip()
            for item in items
        ):
            violations.append(f"{name}_item_incomplete")

    videos = modules.get("video_links")
    if isinstance(videos, list):
        for item in videos:
            if not isinstance(item, dict) or any(
                not str(item.get(key) or "").strip()
                for key in ("account", "title", "screenshot_file")
            ):
                violations.append("related_video_evidence_incomplete")
                break
            if not _artifact_exists(project_root, str(item["screenshot_file"])):
                violations.append("related_video_screenshot_missing")
                break
    return violations


def _artifact_exists(project_root: Path, artifact: str) -> bool:
    return _resolve_project_artifact(project_root, artifact) is not None


def _resolve_project_artifact(project_root: Path, artifact: str) -> Path | None:
    root = project_root.resolve()
    path = Path(artifact)
    candidates = [path] if path.is_absolute() else [root / path, root / "screenshots" / path]
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _screenshot_sections_complete(screenshot_files: list[Any]) -> bool:
    names = {Path(str(filename)).name.lower() for filename in screenshot_files}
    if len(names) < 3:
        return False
    return all(
        any(marker in name for name in names for marker in markers)
        for markers in (
            ("顶部", "top"),
            ("正文", "answer", "body"),
            ("底部", "bottom"),
        )
    )


def _brand_observation_complete(evidence: dict[str, Any], observation: Any) -> bool:
    if (
        not isinstance(observation, dict)
        or observation.get("target") != "高吉星"
        or not isinstance(observation.get("appeared"), bool)
        or not isinstance(observation.get("positions"), list)
    ):
        return False
    basis = str(observation.get("basis") or "").strip()
    if not basis:
        return False
    recommendation = observation.get("natural_recommendation")
    if evidence.get("has_brand") is True:
        return isinstance(recommendation, bool) or (
            recommendation is None and "不判断自然推荐" in basis
        )
    return isinstance(recommendation, bool)
