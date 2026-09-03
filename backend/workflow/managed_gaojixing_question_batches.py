"""Server-managed, per-Run Gaojixing question packages."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import uuid
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from python_calamine import CalamineError, CalamineWorkbook

from backend.config import get_settings
from backend.schemas.workflow import WorkflowProject
from backend.workflow.gaojixing_doubao import parse_gaojixing_question_bank

MAX_QUESTION_BANK_BYTES = 5 * 1024 * 1024
MAX_WORKBOOK_SHEETS = 20
MAX_WORKBOOK_ROWS_PER_SHEET = 5_000
MAX_WORKBOOK_COLUMNS = 100
MAX_WORKBOOK_NON_EMPTY_CELLS = 100_000
MAX_WORKBOOK_MATERIALIZED_CELLS = 500_000
MAX_QUESTIONS = 2_000
MAX_QUESTION_CHARACTERS = 1_000
MAX_XLSX_ENTRIES = 1_000
MAX_XLSX_ENTRY_BYTES = 10 * 1024 * 1024
MAX_XLSX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_XLSX_COMPRESSION_RATIO = 100
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,35}$")
_REFERENCE_VERSION = "qbr1"
_XLS_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
_MANAGED_PACKAGE_IDENTITIES = {
    ("gaojixing-doubao-batch", "package.gaojixing.doubao-batch"),
    ("gaojixing-batch-certification", "package.gaojixing.batch-certification"),
}


class ManagedQuestionBatchError(ValueError):
    """The uploaded question package cannot become a governed Run input."""


class UnsupportedQuestionBatchFormatError(ManagedQuestionBatchError):
    """The uploaded filename does not identify a supported question-bank format."""


class ManagedQuestionBatchConflictError(ManagedQuestionBatchError):
    """The Run is already bound to another immutable question package."""


@dataclass(frozen=True)
class StagedManagedQuestionBatch:
    question_batch_ref: str
    run_id: str
    question_count: int
    created: bool


@dataclass(frozen=True)
class ResolvedManagedQuestionBatch:
    run_id: str
    digest: str
    project_root: Path
    question_bank_path: Path


def accepts_managed_question_batch(project: WorkflowProject) -> bool:
    """Return whether a graph owns both governed Gaojixing package capabilities."""

    identities = {
        (
            str(node.params.get("template") or ""),
            str((node.ui or {}).get("catalogId") or ""),
        )
        for node in project.nodes
    }
    return _MANAGED_PACKAGE_IDENTITIES.issubset(identities)


def stage_managed_question_batch(
    payload: bytes,
    *,
    filename: str,
    run_id: str,
    storage_root: Path | str | None = None,
    signing_key: str | None = None,
) -> StagedManagedQuestionBatch:
    """Validate and atomically freeze one uploaded question package for a Run."""

    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ManagedQuestionBatchError("Run ID is invalid")
    if not payload:
        raise ManagedQuestionBatchError("Question bank is empty")
    if len(payload) > MAX_QUESTION_BANK_BYTES:
        raise ManagedQuestionBatchError("Question bank exceeds the 5 MiB limit")
    document = _parse_question_bank(payload, filename)
    phase_rows, violations = parse_gaojixing_question_bank(document)
    phase_rows = {
        phase: [
            {
                "id": row["id"].strip(),
                "question": row["question"].replace("\u00a0", " ").strip(),
            }
            for row in rows
        ]
        for phase, rows in phase_rows.items()
    }
    for phase, prefix, width in (("phase1", "G", 4), ("phase2", "B", 3)):
        expected_pattern = re.compile(rf"^{prefix}\d{{{width}}}$")
        for index, row in enumerate(phase_rows[phase], start=1):
            question_id = row["id"]
            question = row["question"]
            if not expected_pattern.fullmatch(question_id):
                violations.append(f"question_bank_{phase}_id_invalid:{index}")
            elif question_id != f"{prefix}{index:0{width}d}":
                violations.append(f"question_bank_{phase}_sequence_invalid:{index}")
            if not question:
                violations.append(f"question_bank_{phase}_question_invalid:{index}")
            elif phase == "phase1" and "高吉星" in question:
                violations.append(f"question_bank_phase1_brand_mismatch:{index}")
            elif phase == "phase2" and "高吉星" not in question:
                violations.append(f"question_bank_phase2_brand_mismatch:{index}")
    all_rows = [*phase_rows["phase1"], *phase_rows["phase2"]]
    duplicate_ids = sorted(
        question_id
        for question_id, count in Counter(row["id"] for row in all_rows).items()
        if count > 1
    )
    violations.extend(f"question_bank_duplicate_id:{value}" for value in duplicate_ids)
    if not all_rows:
        violations.append("empty_question_batch")
    if len(all_rows) > MAX_QUESTIONS:
        violations.append(f"question_bank_exceeds_{MAX_QUESTIONS}_questions")
    violations.extend(
        f"question_exceeds_{MAX_QUESTION_CHARACTERS}_characters:{row['id']}"
        for row in all_rows
        if len(row["question"]) > MAX_QUESTION_CHARACTERS
    )
    if violations:
        raise ManagedQuestionBatchError(
            "Question bank failed validation: " + ", ".join(sorted(set(violations)))
        )

    canonical_document = {
        "phase1": phase_rows["phase1"],
        "phase2": phase_rows["phase2"],
    }
    canonical_payload = json.dumps(
        canonical_document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical_payload).hexdigest()
    root = _storage_root(storage_root)
    runs_root = root / "runs"
    run_root = runs_root / run_id
    runs_root.mkdir(parents=True, exist_ok=True)
    temporary_root = runs_root / f".{run_id}.{uuid.uuid4().hex}.tmp"
    temporary_root.mkdir()
    created = False
    try:
        (temporary_root / "raw").mkdir()
        (temporary_root / "screenshots").mkdir()
        (temporary_root / "logs").mkdir()
        (temporary_root / "question-bank.json").write_bytes(canonical_payload)
        try:
            os.rename(temporary_root, run_root)
            created = True
        except OSError:
            existing_path = run_root / "question-bank.json"
            if not existing_path.is_file():
                raise ManagedQuestionBatchConflictError(
                    "A different or incomplete question package already owns this Run"
                )
            existing_digest = hashlib.sha256(existing_path.read_bytes()).hexdigest()
            if not hmac.compare_digest(existing_digest, digest):
                raise ManagedQuestionBatchConflictError(
                    "A different question package already owns this Run"
                )
    finally:
        if temporary_root.exists():
            shutil.rmtree(temporary_root)

    return StagedManagedQuestionBatch(
        question_batch_ref=_encode_reference(run_id, digest, signing_key),
        run_id=run_id,
        question_count=len(all_rows),
        created=created,
    )


def _parse_question_bank(payload: bytes, filename: str) -> dict[str, object]:
    extension = Path(filename).suffix.lower()
    if extension == ".json":
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ManagedQuestionBatchError("Question bank must be valid UTF-8 JSON") from exc
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ManagedQuestionBatchError("Question bank must be valid UTF-8 JSON") from exc
        if not isinstance(document, dict):
            raise ManagedQuestionBatchError("Question bank JSON must be an object")
        return document
    if extension not in {".xls", ".xlsx"}:
        raise UnsupportedQuestionBatchFormatError(
            "Unsupported question bank format; use .json, .xls, or .xlsx"
        )
    if extension == ".xls" and not payload.startswith(_XLS_MAGIC):
        raise ManagedQuestionBatchError("Question bank .xls signature is invalid")
    if extension == ".xlsx":
        if not payload.startswith(b"PK\x03\x04"):
            raise ManagedQuestionBatchError("Question bank .xlsx signature is invalid")
        _validate_xlsx_container(payload)
    workbook = None
    try:
        workbook = CalamineWorkbook.from_filelike(BytesIO(payload))
        if len(workbook.sheet_names) > MAX_WORKBOOK_SHEETS:
            raise ManagedQuestionBatchError(
                f"Question bank exceeds the {MAX_WORKBOOK_SHEETS}-sheet limit"
            )
        sheet_objects = []
        materialized_cells = 0
        for name in workbook.sheet_names:
            sheet = workbook.get_sheet_by_name(name)
            sheet_height = max(sheet.height, sheet.total_height)
            sheet_width = max(sheet.width, sheet.total_width)
            if sheet_height > MAX_WORKBOOK_ROWS_PER_SHEET:
                raise ManagedQuestionBatchError(
                    f"Question bank sheet exceeds the {MAX_WORKBOOK_ROWS_PER_SHEET}-row limit"
                )
            if sheet_width > MAX_WORKBOOK_COLUMNS:
                raise ManagedQuestionBatchError(
                    f"Question bank sheet exceeds the {MAX_WORKBOOK_COLUMNS}-column limit"
                )
            materialized_cells += sheet_height * sheet_width
            if materialized_cells > MAX_WORKBOOK_MATERIALIZED_CELLS:
                raise ManagedQuestionBatchError(
                    "Question bank exceeds the workbook materialization limit"
                )
            sheet_objects.append(sheet)
        sheets = [sheet.to_python() for sheet in sheet_objects]
    except ManagedQuestionBatchError:
        raise
    except (CalamineError, OSError, ValueError) as exc:
        raise ManagedQuestionBatchError("Question bank Excel workbook is unreadable") from exc
    finally:
        if workbook is not None:
            workbook.close()
    return _question_bank_from_sheet_rows(sheets)


def _validate_xlsx_container(payload: bytes) -> None:
    try:
        with ZipFile(BytesIO(payload)) as archive:
            entries = archive.infolist()
    except BadZipFile as exc:
        raise ManagedQuestionBatchError("Question bank .xlsx container is invalid") from exc
    if len(entries) > MAX_XLSX_ENTRIES:
        raise ManagedQuestionBatchError("Question bank .xlsx has too many archive entries")
    uncompressed_total = 0
    for entry in entries:
        name = entry.filename.replace("\\", "/")
        lowered = name.lower()
        if name.startswith("/") or ".." in Path(name).parts:
            raise ManagedQuestionBatchError("Question bank .xlsx archive path is unsafe")
        if entry.flag_bits & 0x1:
            raise ManagedQuestionBatchError("Question bank .xlsx is encrypted")
        if "vbaproject" in lowered or lowered.endswith(".bin"):
            raise ManagedQuestionBatchError("Question bank .xlsx macros are not allowed")
        if entry.file_size > MAX_XLSX_ENTRY_BYTES:
            raise ManagedQuestionBatchError("Question bank .xlsx archive entry is too large")
        uncompressed_total += entry.file_size
        if uncompressed_total > MAX_XLSX_UNCOMPRESSED_BYTES:
            raise ManagedQuestionBatchError("Question bank .xlsx expands beyond its size limit")
        if entry.file_size and (
            entry.compress_size == 0
            or entry.file_size > entry.compress_size * MAX_XLSX_COMPRESSION_RATIO
        ):
            raise ManagedQuestionBatchError(
                "Question bank .xlsx archive compression ratio is unsafe"
            )


def _question_bank_from_sheet_rows(
    sheets: list[list[list[object]]],
) -> dict[str, list[dict[str, str]]]:
    phase1: list[dict[str, str]] = []
    phase2: list[dict[str, str]] = []
    phase1_index = 0
    phase2_index = 0
    non_empty_cells = 0
    for rows in sheets:
        if len(rows) > MAX_WORKBOOK_ROWS_PER_SHEET:
            raise ManagedQuestionBatchError(
                f"Question bank sheet exceeds the {MAX_WORKBOOK_ROWS_PER_SHEET}-row limit"
            )
        width = max((len(row) for row in rows), default=0)
        if width > MAX_WORKBOOK_COLUMNS:
            raise ManagedQuestionBatchError(
                f"Question bank sheet exceeds the {MAX_WORKBOOK_COLUMNS}-column limit"
            )
        non_empty_cells += sum(
            1 for row in rows for value in row if _cell_is_non_empty(value)
        )
        if non_empty_cells > MAX_WORKBOOK_NON_EMPTY_CELLS:
            raise ManagedQuestionBatchError("Question bank has too many non-empty cells")
        eligible_columns = {
            column
            for column in range(width)
            if sum(1 for row in rows if column < len(row) and _cell_is_non_empty(row[column])) > 1
        }
        for row in rows:
            for column, value in enumerate(row):
                if column not in eligible_columns or not isinstance(value, str):
                    continue
                question = value.replace("\u00a0", " ").strip()
                if not question:
                    continue
                if len(question) > MAX_QUESTION_CHARACTERS:
                    raise ManagedQuestionBatchError(
                        f"Question exceeds the {MAX_QUESTION_CHARACTERS}-character limit"
                    )
                if "高吉星" in question:
                    phase2_index += 1
                    phase2.append({"id": f"B{phase2_index:03d}", "question": question})
                else:
                    phase1_index += 1
                    phase1.append({"id": f"G{phase1_index:04d}", "question": question})
                if phase1_index + phase2_index > MAX_QUESTIONS:
                    raise ManagedQuestionBatchError(
                        f"Question bank exceeds the {MAX_QUESTIONS}-question limit"
                    )
    return {"phase1": phase1, "phase2": phase2}


def _cell_is_non_empty(value: object) -> bool:
    return bool(value.strip()) if isinstance(value, str) else value is not None


def resolve_managed_question_batch(
    question_batch_ref: str,
    *,
    expected_run_id: str | None = None,
    storage_root: Path | str | None = None,
    signing_key: str | None = None,
) -> ResolvedManagedQuestionBatch:
    """Verify an opaque Run input and resolve its server-owned paths."""

    run_id, digest = _decode_reference(question_batch_ref, signing_key)
    if expected_run_id is not None and run_id != expected_run_id:
        raise ManagedQuestionBatchError("Question package belongs to a different run")
    root = _storage_root(storage_root)
    runs_root = (root / "runs").resolve()
    project_root = (runs_root / run_id).resolve()
    try:
        project_root.relative_to(runs_root)
    except ValueError as exc:
        raise ManagedQuestionBatchError("Question package reference is invalid") from exc
    if project_root.parent != runs_root:
        raise ManagedQuestionBatchError("Question package reference is invalid")
    question_bank_path = project_root / "question-bank.json"
    if not question_bank_path.is_file():
        raise ManagedQuestionBatchError("Question package content is missing")
    stored_digest = hashlib.sha256(question_bank_path.read_bytes()).hexdigest()
    if not hmac.compare_digest(stored_digest, digest):
        raise ManagedQuestionBatchError("Question package content failed integrity validation")
    return ResolvedManagedQuestionBatch(
        run_id=run_id,
        digest=digest,
        project_root=project_root,
        question_bank_path=question_bank_path,
    )


def cleanup_managed_question_batch(
    question_batch_ref: str,
    *,
    expected_run_id: str,
    storage_root: Path | str | None = None,
    signing_key: str | None = None,
) -> bool:
    """Delete one verified per-Run package after its owning Run failed to start."""

    resolved = resolve_managed_question_batch(
        question_batch_ref,
        expected_run_id=expected_run_id,
        storage_root=storage_root,
        signing_key=signing_key,
    )
    runs_root = (_storage_root(storage_root) / "runs").resolve()
    if resolved.project_root.parent != runs_root or resolved.project_root.name != expected_run_id:
        raise ManagedQuestionBatchError("Question package cleanup target is invalid")
    shutil.rmtree(resolved.project_root)
    return True


def _storage_root(value: Path | str | None) -> Path:
    configured = value if value is not None else get_settings().gaojixing_run_storage_path
    return Path(configured).resolve()


def _signing_key(value: str | None) -> bytes:
    configured = value if value is not None else get_settings().secret_key
    if not configured:
        raise ManagedQuestionBatchError("Question package signing key is unavailable")
    return configured.encode("utf-8")


def _encode_reference(run_id: str, digest: str, signing_key: str | None) -> str:
    claims = json.dumps(
        {"digest": digest, "runId": run_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_claims = _base64_encode(claims)
    signature = hmac.new(
        _signing_key(signing_key),
        f"{_REFERENCE_VERSION}.{encoded_claims}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{_REFERENCE_VERSION}.{encoded_claims}.{_base64_encode(signature)}"


def _decode_reference(value: str, signing_key: str | None) -> tuple[str, str]:
    try:
        version, encoded_claims, encoded_signature = value.split(".")
        if version != _REFERENCE_VERSION:
            raise ValueError
        expected_signature = hmac.new(
            _signing_key(signing_key),
            f"{version}.{encoded_claims}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        supplied_signature = _base64_decode(encoded_signature)
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise ValueError
        claims = json.loads(_base64_decode(encoded_claims))
        run_id = claims["runId"]
        digest = claims["digest"]
        if (
            not isinstance(run_id, str)
            or not _RUN_ID_PATTERN.fullmatch(run_id)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagedQuestionBatchError("Question package reference is invalid") from exc
    return run_id, digest


def _base64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
