"""Structural terminal certification for a Gaojixing Doubao evidence batch.

Screenshot checks cover governed paths, references, distinct section files and
hashes. They do not authenticate screenshot pixels or OCR content.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from backend.workflow.gaojixing_doubao import (
    audit_gaojixing_question_evidence,
    resolve_registered_fixture_root,
)

GAOJIXING_BATCH_CERTIFY_TOOL_ID = "tool.gaojixing.batch-certify"
GAOJIXING_BATCH_CERTIFY_EXECUTOR = "gaojixing_batch_certify"


async def execute_gaojixing_batch_certification(
    input_items: list[dict[str, Any]],
    params: dict[str, Any],
) -> dict[str, Any]:
    """Certify either an upstream fixture result or a real 2.2 project directory."""

    policy_version = str(params.get("policyVersion") or "2.2")
    phase1_expected = _positive_count(params, "phase1Expected")
    phase2_expected = _positive_count(params, "phase2Expected")
    source_mode = str(params.get("sourceMode") or "").strip()
    project_root_value = str(params.get("projectRoot") or "").strip()
    evidence_digest: str | None = None
    if source_mode not in {"offline_fixture", "project_archive"}:
        counts, violations = _counts(0, 0), ["unsupported_source_mode"]
    elif source_mode == "project_archive":
        project_root = Path(project_root_value)
        question_bank_path = Path(str(params.get("questionBankPath") or ""))
        counts, violations = _certify_project_root(
            project_root,
            question_bank_path=question_bank_path,
            phase1_expected=phase1_expected,
            phase2_expected=phase2_expected,
        )
        evidence_digest = _evidence_digest(project_root, question_bank_path)
    else:
        evidence_root = _trusted_upstream_evidence_root(params)
        counts, violations = _certify_upstream_batch(
            input_items,
            phase1_expected=phase1_expected,
            phase2_expected=phase2_expected,
            evidence_root=evidence_root,
        )
    result = {
        "schema": "gaojixing.batch-certification.v1",
        "status": "certified" if not violations else "rejected",
        "policyVersion": policy_version,
        "counts": counts,
        "violations": violations,
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
    if evidence_digest is not None:
        result["evidenceDigest"] = evidence_digest
    return result


def _certify_upstream_batch(
    input_items: list[dict[str, Any]],
    *,
    phase1_expected: int,
    phase2_expected: int,
    evidence_root: Path | None,
) -> tuple[dict[str, int], list[str]]:
    batch = next(
        (
            candidate
            for item in input_items
            for candidate in (
                item.get("raw"),
                item.get("normalizedData"),
                item,
            )
            if isinstance(candidate, dict)
            and candidate.get("schema") == "gaojixing.doubao-batch-result.v1"
        ),
        None,
    )
    if batch is None:
        return _counts(0, 0), ["upstream_batch_result_missing"]
    phase_counts = batch.get("phaseCounts")
    if not isinstance(phase_counts, dict):
        return _counts(0, 0), ["upstream_phase_counts_missing"]
    phase1_value = phase_counts.get("stage1_non_brand")
    phase2_value = phase_counts.get("stage2_brand")
    phase1 = phase1_value if isinstance(phase1_value, int) else 0
    phase2 = phase2_value if isinstance(phase2_value, int) else 0
    total_expected = phase1_expected + phase2_expected
    violations: list[str] = []
    if batch.get("status") != "completed":
        violations.append("upstream_batch_not_completed")
    if phase1 != phase1_expected:
        violations.append("phase1_count_mismatch")
    if phase2 != phase2_expected:
        violations.append("phase2_count_mismatch")

    record_count = batch.get("recordCount")
    if (
        not isinstance(record_count, int)
        or isinstance(record_count, bool)
        or record_count != total_expected
    ):
        violations.append("upstream_record_count_mismatch")

    accepted_ids = batch.get("acceptedQuestionIds")
    accepted_valid = (
        isinstance(accepted_ids, list)
        and len(accepted_ids) == total_expected
        and all(isinstance(question_id, str) and question_id for question_id in accepted_ids)
        and len(set(accepted_ids)) == len(accepted_ids)
    )
    if not accepted_valid:
        violations.append("upstream_accepted_question_ids_invalid")

    audits = batch.get("audits")
    audit_ids = (
        [audit.get("questionId") for audit in audits if isinstance(audit, dict)]
        if isinstance(audits, list)
        else []
    )
    if not isinstance(audits, list) or len(audits) != total_expected:
        violations.append("upstream_audit_count_mismatch")
    if (
        not isinstance(audits, list)
        or len(audit_ids) != len(audits)
        or any(not isinstance(question_id, str) or not question_id for question_id in audit_ids)
        or len(set(audit_ids)) != len(audit_ids)
    ):
        violations.append("upstream_audit_question_ids_invalid")
    elif accepted_valid and set(audit_ids) != set(accepted_ids):
        violations.append("upstream_audit_question_ids_mismatch")
    if not isinstance(audits, list) or any(
        not isinstance(audit, dict)
        or audit.get("status") != "passed"
        or audit.get("violations") != []
        for audit in audits
    ):
        violations.append("upstream_question_audit_failed")
    if batch.get("batchViolations") != []:
        violations.append("upstream_batch_violations_present")
    if batch.get("searchTriggered") is not False:
        violations.append("upstream_search_triggered_not_false")

    governed_id = re.compile(r"(?:G\d{4}|B\d{3})\Z")
    if accepted_valid and any(
        governed_id.fullmatch(question_id) is None for question_id in accepted_ids
    ):
        violations.append("upstream_accepted_question_id_format_invalid")

    evidence = batch.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        violations.append("upstream_evidence_missing")
        return _counts(0, 0), sorted(set(violations))
    if len(evidence) != total_expected:
        violations.append("upstream_evidence_count_mismatch")
    evidence_ids = [
        item.get("id") for item in evidence if isinstance(item, dict)
    ]
    evidence_ids_valid = (
        len(evidence_ids) == len(evidence)
        and all(
            isinstance(question_id, str) and bool(question_id)
            for question_id in evidence_ids
        )
        and len(set(evidence_ids)) == len(evidence_ids)
    )
    if not evidence_ids_valid:
        violations.append("upstream_evidence_question_ids_invalid")
    elif accepted_valid and set(evidence_ids) != set(accepted_ids):
        violations.append("upstream_evidence_question_ids_mismatch")

    evidence_phase1 = sum(
        1
        for question_id in evidence_ids
        if isinstance(question_id, str) and re.fullmatch(r"G\d{4}", question_id)
    )
    evidence_phase2 = sum(
        1
        for question_id in evidence_ids
        if isinstance(question_id, str) and re.fullmatch(r"B\d{3}", question_id)
    )
    if phase1 != evidence_phase1 or phase2 != evidence_phase2:
        violations.append("upstream_phase_counts_evidence_mismatch")

    if evidence_root is None or not evidence_root.is_dir():
        violations.append("upstream_evidence_root_missing")
        return _counts(evidence_phase1, evidence_phase2), sorted(set(violations))
    trusted_root = evidence_root.resolve()
    reported_root = batch.get("evidenceRoot")
    if isinstance(reported_root, str) and reported_root.strip():
        if Path(reported_root).resolve() != trusted_root:
            violations.append("upstream_evidence_root_mismatch")

    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            violations.append(f"upstream_evidence_invalid:{index}")
            continue
        question_id = str(item.get("id") or index)
        violations.extend(
            f"upstream_evidence_audit_failed:{question_id}:{violation}"
            for violation in audit_gaojixing_question_evidence(
                item,
                project_root=trusted_root,
            )
        )
    return _counts(evidence_phase1, evidence_phase2), sorted(set(violations))


def _trusted_upstream_evidence_root(params: dict[str, Any]) -> Path | None:
    configured_root = str(params.get("projectRoot") or "").strip()
    if configured_root:
        return Path(configured_root).resolve()
    fixture_id = str(params.get("fixtureId") or "").strip()
    return resolve_registered_fixture_root(fixture_id)


def _certify_project_root(
    project_root: Path,
    *,
    question_bank_path: Path,
    phase1_expected: int,
    phase2_expected: int,
) -> tuple[dict[str, int], list[str]]:
    violations: list[str] = []
    if not project_root.is_dir():
        return _counts(0, 0), ["project_root_missing"]
    question_bank = _read_json(question_bank_path, "question_bank", violations)
    phase1_bank = _question_rows(question_bank, "phase1")
    phase2_bank = _question_rows(question_bank, "phase2")
    if len(phase1_bank) != phase1_expected:
        violations.append("question_bank_phase1_count_mismatch")
    if len(phase2_bank) != phase2_expected:
        violations.append("question_bank_phase2_count_mismatch")
    question_id_counts = Counter(
        row["id"] for row in [*phase1_bank, *phase2_bank]
    )
    violations.extend(
        f"question_bank_duplicate_id:{question_id}"
        for question_id, count in sorted(question_id_counts.items())
        if count > 1
    )

    expected = {row["id"]: row["question"] for row in [*phase1_bank, *phase2_bank]}
    raw_dir = project_root / "raw"
    raw_paths = {path.stem: path for path in raw_dir.glob("*.json")} if raw_dir.is_dir() else {}
    missing_ids = sorted(set(expected) - set(raw_paths))
    extra_ids = sorted(set(raw_paths) - set(expected))
    violations.extend(f"raw_missing:{question_id}" for question_id in missing_ids)
    violations.extend(f"raw_unexpected:{question_id}" for question_id in extra_ids)

    records: dict[str, dict[str, Any]] = {}
    for question_id in sorted(set(expected) & set(raw_paths)):
        record = _read_json(raw_paths[question_id], f"raw:{question_id}", violations)
        if not isinstance(record, dict):
            continue
        records[question_id] = record
        if record.get("id") != question_id:
            violations.append(f"raw_id_mismatch:{question_id}")
        if record.get("question") != expected[question_id]:
            violations.append(f"original_question_mismatch:{question_id}")
        violations.extend(
            f"{question_id}:{violation}"
            for violation in audit_gaojixing_question_evidence(
                record,
                project_root=project_root,
            )
        )

    phase1_archive = _markdown_sections(_read_text(project_root / "阶段1_非品牌问句归档.md"))
    phase2_archive = _markdown_sections(_read_text(project_root / "阶段2_品牌问句归档.md"))
    for question_id, record in records.items():
        archive = phase2_archive if question_id.startswith("B") else phase1_archive
        section = archive.get(question_id)
        if section is None:
            violations.append(f"markdown_entry_missing:{question_id}")
            continue
        violations.extend(_audit_markdown_section(question_id, record, section))

    status = _read_json(project_root / "任务状态.json", "task_status", violations)
    total_expected = phase1_expected + phase2_expected
    if not isinstance(status, dict):
        violations.append("task_status_invalid")
    else:
        if status.get("completed_count") != total_expected:
            violations.append("task_status_completed_count_mismatch")
        if status.get("phase1_complete") is not True:
            violations.append("task_status_phase1_not_complete")
        if status.get("phase2_complete") is not True:
            violations.append("task_status_phase2_not_complete")
        final = status.get("final_summary")
        if not isinstance(final, dict) or final.get("status") != "ALL COMPLETE":
            violations.append("task_status_final_summary_incomplete")
        elif (
            final.get("total_raw") != total_expected
            or not _summary_matches(final.get("phase1"), phase1_expected)
            or not _summary_matches(final.get("phase2"), phase2_expected)
        ):
            violations.append("task_status_final_summary_count_mismatch")

    progress = _read_text(project_root / "进度日志.md")
    if not _progress_has_count(progress, "阶段1", phase1_expected):
        violations.append("progress_stage1_count_mismatch")
    if not _progress_has_count(progress, "阶段2", phase2_expected):
        violations.append("progress_stage2_count_mismatch")

    phase1_count = sum(question_id.startswith("G") for question_id in records)
    phase2_count = sum(question_id.startswith("B") for question_id in records)
    if phase1_count != phase1_expected:
        violations.append("raw_phase1_count_mismatch")
    if phase2_count != phase2_expected:
        violations.append("raw_phase2_count_mismatch")
    return _counts(phase1_count, phase2_count), sorted(set(violations))


def _read_json(path: Path, label: str, violations: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        violations.append(f"{label}_unreadable")
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _markdown_sections(archive: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    pattern = re.compile(r"(?ms)^## ((?:G\d{4}|B\d{3}))｜.*?(?=^## |\Z)")
    for match in pattern.finditer(archive.replace("\r\n", "\n")):
        sections[match.group(1)] = match.group(0).rstrip()
    return sections


def _audit_markdown_section(
    question_id: str,
    record: dict[str, Any],
    section: str,
) -> list[str]:
    violations: list[str] = []
    question = str(record.get("question") or "")
    if not section.startswith(f"## {question_id}｜{question}\n") or (
        f"- 原问句：{question}" not in section
    ):
        violations.append(f"markdown_question_mismatch:{question_id}")
    if "- 状态：已完成" not in section:
        violations.append(f"markdown_status_mismatch:{question_id}")
    chat_url = str(record.get("chat_url") or "")
    if f"- 豆包会话 URL（原文）：{chat_url}" not in section:
        violations.append(f"markdown_chat_url_missing:{question_id}")
    collected_at = str(record.get("collected_at") or "")
    if f"- 采集时间：{collected_at}" not in section:
        violations.append(f"markdown_collected_at_mismatch:{question_id}")
    if _markdown_answer(section) != _normalize_text(str(record.get("answer") or "")):
        violations.append(f"markdown_answer_mismatch:{question_id}")

    modules = record.get("page_modules")
    if isinstance(modules, dict):
        for module_name, label in (
            ("keywords", "页面显示的关键词"),
            ("ref_links", "参考资料"),
            ("product_links", "产品外链"),
            ("video_links", "相关视频"),
            ("followups", "推荐追问"),
        ):
            if not _markdown_module_matches(
                section,
                label=label,
                module_name=module_name,
                value=modules.get(module_name),
            ):
                violations.append(f"markdown_module_{module_name}_mismatch:{question_id}")

    if not _markdown_brand_observation_matches(section, record.get("brand_observation")):
        violations.append(f"markdown_brand_observation_mismatch:{question_id}")

    page_evidence = record.get("page_evidence")
    screenshot_files = (
        page_evidence.get("screenshot_files") if isinstance(page_evidence, dict) else None
    )
    if not isinstance(screenshot_files, list) or any(
        Path(str(filename)).name not in section for filename in screenshot_files
    ):
        violations.append(f"markdown_screenshot_reference_mismatch:{question_id}")
    return violations


def _markdown_answer(section: str) -> str:
    heading = re.search(r"(?m)^- 回答原文(?:（[^\n]*）)?：\s*$", section)
    if heading is None:
        return ""
    answer_lines: list[str] = []
    started = False
    for line in section[heading.end() :].splitlines():
        if line.startswith(">"):
            started = True
            answer_lines.append(line[2:] if line.startswith("> ") else line[1:])
        elif started:
            break
    return _normalize_text("\n".join(answer_lines))


def _normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def _markdown_module_matches(
    section: str,
    *,
    label: str,
    module_name: str,
    value: Any,
) -> bool:
    block = _markdown_field_block(section, label)
    if block is None:
        return False
    if value == "页面未显示":
        return block.splitlines()[0].strip() == f"- {label}：页面未显示"
    if not isinstance(value, list) or not value:
        return False
    heading = block.splitlines()[0]
    if re.search(rf"（\s*{len(value)}\s*(?:项|篇)", heading) is None:
        return False
    return all(token in block for item in value for token in _module_item_tokens(module_name, item))


def _markdown_field_block(section: str, label: str) -> str | None:
    match = re.search(rf"(?m)^- {re.escape(label)}[^\n]*$", section)
    if match is None:
        return None
    remainder = section[match.end() :]
    next_field = re.search(r"(?m)^- \S", remainder)
    end = match.end() + next_field.start() if next_field is not None else len(section)
    return section[match.start() : end].rstrip()


def _module_item_tokens(module_name: str, item: Any) -> list[str]:
    if isinstance(item, str):
        return [item]
    if not isinstance(item, dict):
        return [str(item)]
    required_keys = {
        "ref_links": ("title", "url"),
        "video_links": ("account", "title", "screenshot_file"),
    }.get(module_name)
    if required_keys is not None:
        return [str(item.get(key) or "") for key in required_keys]
    return [str(value) for value in item.values() if value not in (None, "")]


def _markdown_brand_observation_matches(section: str, observation: Any) -> bool:
    if not isinstance(observation, dict):
        return False
    appeared = observation.get("appeared")
    if not isinstance(appeared, bool) or (
        f"- 高吉星是否出现：{'是' if appeared else '否'}" not in section
    ):
        return False
    positions = observation.get("positions")
    positions_block = _markdown_field_block(section, "高吉星出现位置")
    if not isinstance(positions, list) or positions_block is None:
        return False
    if not positions:
        if "页面未出现" not in positions_block:
            return False
    elif any(
        token not in positions_block
        for item in positions
        for token in _position_tokens(item)
    ):
        return False
    recommendation = observation.get("natural_recommendation")
    basis = str(observation.get("basis") or "")
    conclusion = _markdown_field_block(section, "自然推荐结论")
    if not basis or conclusion is None or basis not in conclusion:
        return False
    if recommendation is None:
        return "不适用" in conclusion
    if not isinstance(recommendation, bool):
        return False
    return f"自然推荐结论：{'是' if recommendation else '否'}" in conclusion


def _position_tokens(item: Any) -> list[str]:
    if isinstance(item, str):
        return [item]
    if not isinstance(item, dict):
        return [str(item)]
    return [
        str(item.get(key) or "")
        for key in ("module", "text")
        if str(item.get(key) or "")
    ]


def _question_rows(document: Any, phase: str) -> list[dict[str, str]]:
    if not isinstance(document, dict) or not isinstance(document.get(phase), list):
        return []
    return [
        {"id": str(row["id"]), "question": str(row["question"])}
        for row in document[phase]
        if isinstance(row, dict) and row.get("id") and row.get("question")
    ]


def _positive_count(params: dict[str, Any], name: str) -> int:
    value = params.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name}_must_be_positive")
    return value


def _counts(phase1: int, phase2: int) -> dict[str, int]:
    return {
        "stage1_non_brand": phase1,
        "stage2_brand": phase2,
        "total": phase1 + phase2,
    }


def _summary_matches(value: Any, expected: int) -> bool:
    return isinstance(value, dict) and all(
        value.get(field) == expected for field in ("total", "completed", "archive_entries")
    )


def _progress_has_count(progress: str, phase_label: str, expected: int) -> bool:
    return bool(
        re.search(
            rf"{re.escape(phase_label)}[^\n]*已完成[^\n]*{expected}\s*/\s*{expected}",
            progress,
        )
    )


def _evidence_digest(project_root: Path, question_bank_path: Path) -> str:
    artifacts: dict[str, Path | None] = {
        "question_bank": question_bank_path,
        "archive/phase1": project_root / "阶段1_非品牌问句归档.md",
        "archive/phase2": project_root / "阶段2_品牌问句归档.md",
        "status": project_root / "任务状态.json",
        "progress": project_root / "进度日志.md",
    }
    raw_dir = project_root / "raw"
    for raw_path in sorted(raw_dir.glob("*.json")) if raw_dir.is_dir() else []:
        artifacts[f"raw/{raw_path.name}"] = raw_path
        try:
            record = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for artifact in _record_screenshot_artifacts(record):
            resolved = _resolve_artifact_path(project_root, artifact)
            if resolved is None:
                invalid_label = hashlib.sha256(artifact.encode("utf-8")).hexdigest()
                artifacts[f"screenshot/invalid/{invalid_label}"] = None
                continue
            relative = resolved.relative_to(project_root.resolve()).as_posix()
            artifacts[f"screenshot/{relative}"] = resolved

    digest = hashlib.sha256()
    for label, path in sorted(artifacts.items()):
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        if path is None or not path.is_file():
            digest.update(b"missing")
            continue
        digest.update(_sha256_file(path))
    return digest.hexdigest()


def _record_screenshot_artifacts(record: Any) -> set[str]:
    if not isinstance(record, dict):
        return set()
    artifacts: set[str] = set()
    page_evidence = record.get("page_evidence")
    if isinstance(page_evidence, dict) and isinstance(
        page_evidence.get("screenshot_files"), list
    ):
        artifacts.update(str(value) for value in page_evidence["screenshot_files"])
    modules = record.get("page_modules")
    videos = modules.get("video_links") if isinstance(modules, dict) else None
    if isinstance(videos, list):
        artifacts.update(
            str(video.get("screenshot_file"))
            for video in videos
            if isinstance(video, dict) and video.get("screenshot_file")
        )
    return artifacts


def _resolve_artifact_path(project_root: Path, artifact: str) -> Path | None:
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


def _sha256_file(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()
