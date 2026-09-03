# ruff: noqa: E501

import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.workflow import managed_gaojixing_question_batches as managed_batches
from backend.workflow.managed_gaojixing_question_batches import (
    ManagedQuestionBatchError,
    cleanup_managed_question_batch,
    resolve_managed_question_batch,
    stage_managed_question_batch,
)


def _question_bank_bytes() -> bytes:
    return json.dumps(
        {
            "phase1": [{"id": "G0001", "question": "孕妇 DHA 怎么选？"}],
            "phase2": [{"id": "B001", "question": "高吉星 DHA 怎么样？"}],
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _xlsx_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
              <Default Extension="xml" ContentType="application/xml"/>
              <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
              <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
            </Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
            </Relationships>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets><sheet name="孕妇钙片" sheetId="1" r:id="rId1"/></sheets>
            </workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
            </Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="inlineStr"><is><t>孕妇钙片怎么选？</t></is></c><c r="B1" t="inlineStr"><is><t>作者甲</t></is></c><c r="C1" t="inlineStr"><is><t>作者乙</t></is></c></row>
                <row r="2"><c r="A2" t="inlineStr"><is><t>高吉星 DHA 怎么样？</t></is></c></row>
                <row r="3"><c r="A3" t="inlineStr"><is><t>普通 DHA 推荐</t></is></c></row>
              </sheetData>
            </worksheet>""",
        )
    return output.getvalue()


def test_stage_managed_question_batch_returns_only_an_opaque_reference(tmp_path):
    staged = stage_managed_question_batch(
        _question_bank_bytes(),
        filename="questions.json",
        run_id="run-upload-1",
        storage_root=tmp_path,
        signing_key="test-signing-key",
    )

    assert staged.question_batch_ref.startswith("qbr1.")
    assert str(tmp_path) not in staged.question_batch_ref
    assert staged.run_id == "run-upload-1"
    assert staged.question_count == 2
    assert staged.created is True

    resolved = resolve_managed_question_batch(
        staged.question_batch_ref,
        storage_root=tmp_path,
        signing_key="test-signing-key",
    )
    assert resolved.project_root == (tmp_path / "runs" / "run-upload-1").resolve()
    assert resolved.question_bank_path == resolved.project_root / "question-bank.json"
    assert json.loads(resolved.question_bank_path.read_text(encoding="utf-8")) == {
        "phase1": [{"id": "G0001", "question": "孕妇 DHA 怎么选？"}],
        "phase2": [{"id": "B001", "question": "高吉星 DHA 怎么样？"}],
    }

    repeated = stage_managed_question_batch(
        _question_bank_bytes(),
        filename="questions.json",
        run_id="run-upload-1",
        storage_root=tmp_path,
        signing_key="test-signing-key",
    )
    assert repeated.question_batch_ref == staged.question_batch_ref
    assert repeated.created is False
    assert cleanup_managed_question_batch(
        staged.question_batch_ref,
        expected_run_id="run-upload-1",
        storage_root=tmp_path,
        signing_key="test-signing-key",
    )
    assert not resolved.project_root.exists()


def test_stage_managed_question_batch_rejects_invalid_or_oversized_input(tmp_path):
    with pytest.raises(ManagedQuestionBatchError, match="UTF-8"):
        stage_managed_question_batch(
            b"\xff",
            filename="questions.json",
            run_id="run-invalid-utf8",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )

    with pytest.raises(ManagedQuestionBatchError, match="phase2"):
        stage_managed_question_batch(
            b'{"phase1": []}',
            filename="questions.json",
            run_id="run-invalid-schema",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )

    with pytest.raises(ManagedQuestionBatchError, match="5 MiB"):
        stage_managed_question_batch(
            b"x" * (5 * 1024 * 1024 + 1),
            filename="questions.json",
            run_id="run-too-large",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )


def test_managed_question_batch_reference_is_run_bound_and_tamper_evident(tmp_path):
    staged = stage_managed_question_batch(
        _question_bank_bytes(),
        filename="questions.json",
        run_id="run-upload-2",
        storage_root=tmp_path,
        signing_key="test-signing-key",
    )

    with pytest.raises(ManagedQuestionBatchError, match="invalid"):
        resolve_managed_question_batch(
            staged.question_batch_ref + "tampered",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )

    with pytest.raises(ManagedQuestionBatchError, match="different run"):
        resolve_managed_question_batch(
            staged.question_batch_ref,
            expected_run_id="run-upload-other",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )


def test_stage_managed_question_batch_converts_excel_columns_deterministically(tmp_path):
    staged = stage_managed_question_batch(
        _xlsx_bytes(),
        filename="questions.xlsx",
        run_id="run-upload-xlsx",
        storage_root=tmp_path,
        signing_key="test-signing-key",
    )
    resolved = resolve_managed_question_batch(
        staged.question_batch_ref,
        storage_root=tmp_path,
        signing_key="test-signing-key",
    )

    assert json.loads(resolved.question_bank_path.read_text(encoding="utf-8")) == {
        "phase1": [
            {"id": "G0001", "question": "孕妇钙片怎么选？"},
            {"id": "G0002", "question": "普通 DHA 推荐"},
        ],
        "phase2": [{"id": "B001", "question": "高吉星 DHA 怎么样？"}],
    }

    with pytest.raises(ManagedQuestionBatchError, match="Unsupported"):
        stage_managed_question_batch(
            b"question",
            filename="questions.csv",
            run_id="run-upload-csv",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )


def test_stage_managed_question_batch_rejects_unsafe_excel_containers(tmp_path):
    with pytest.raises(ManagedQuestionBatchError, match="empty"):
        stage_managed_question_batch(
            b"",
            filename="questions.xls",
            run_id="run-empty-xls",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )

    with pytest.raises(ManagedQuestionBatchError, match="signature"):
        stage_managed_question_batch(
            b"not-an-excel-workbook",
            filename="questions.xls",
            run_id="run-invalid-xls",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )

    macro_workbook = BytesIO()
    with ZipFile(macro_workbook, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/vbaProject.bin", b"macro")
    with pytest.raises(ManagedQuestionBatchError, match="macro"):
        stage_managed_question_batch(
            macro_workbook.getvalue(),
            filename="questions.xlsx",
            run_id="run-macro-xlsx",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )


def test_excel_rejects_aggregate_materialization_before_any_sheet_is_decoded(
    tmp_path, monkeypatch
):
    decoded_sheets: list[str] = []

    class FakeSheet:
        height = 5_000
        width = 100
        total_height = 5_000
        total_width = 100

        def __init__(self, name: str):
            self.name = name

        def to_python(self):
            decoded_sheets.append(self.name)
            return []

    class FakeWorkbook:
        sheet_names = ["sheet-1", "sheet-2"]

        def get_sheet_by_name(self, name: str):
            return FakeSheet(name)

        def close(self):
            return None

    class FakeCalamineWorkbook:
        @staticmethod
        def from_filelike(_payload):
            return FakeWorkbook()

    monkeypatch.setattr(
        managed_batches,
        "CalamineWorkbook",
        FakeCalamineWorkbook,
    )
    with pytest.raises(ManagedQuestionBatchError, match="materialization"):
        stage_managed_question_batch(
            bytes.fromhex("D0CF11E0A1B11AE1") + b"fake-workbook",
            filename="questions.xls",
            run_id="run-materialization-limit",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )

    assert decoded_sheets == []


def test_stage_managed_question_batch_enforces_question_limits_and_normalizes_nbsp(tmp_path):
    oversized_question = json.dumps(
        {
            "phase1": [{"id": "G0001", "question": "x" * 1001}],
            "phase2": [],
        }
    ).encode()
    with pytest.raises(ManagedQuestionBatchError, match="1000"):
        stage_managed_question_batch(
            oversized_question,
            filename="questions.json",
            run_id="run-long-question",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )

    too_many_questions = json.dumps(
        {
            "phase1": [
                {"id": f"G{index:04d}", "question": f"question {index}"}
                for index in range(1, 2002)
            ],
            "phase2": [],
        }
    ).encode()
    with pytest.raises(ManagedQuestionBatchError, match="2000"):
        stage_managed_question_batch(
            too_many_questions,
            filename="questions.json",
            run_id="run-many-questions",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )

    staged = stage_managed_question_batch(
        json.dumps(
            {
                "phase1": [{"id": "G0001", "question": " 孕妇\u00a0DHA 怎么选？ "}],
                "phase2": [],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        filename="questions.json",
        run_id="run-normalized-nbsp",
        storage_root=tmp_path,
        signing_key="test-signing-key",
    )
    resolved = resolve_managed_question_batch(
        staged.question_batch_ref,
        storage_root=tmp_path,
        signing_key="test-signing-key",
    )
    assert json.loads(resolved.question_bank_path.read_text(encoding="utf-8"))[
        "phase1"
    ][0]["question"] == "孕妇 DHA 怎么选？"


@pytest.mark.parametrize(
    ("document", "violation"),
    [
        (
            {"phase1": [{"id": "question-1", "question": "普通题"}], "phase2": []},
            "phase1_id",
        ),
        (
            {"phase1": [{"id": "G0002", "question": "普通题"}], "phase2": []},
            "phase1_sequence",
        ),
        (
            {"phase1": [], "phase2": [{"id": "B01", "question": "高吉星题"}]},
            "phase2_id",
        ),
        (
            {"phase1": [{"id": "G0001", "question": "高吉星题"}], "phase2": []},
            "phase1_brand",
        ),
        (
            {"phase1": [], "phase2": [{"id": "B001", "question": "普通题"}]},
            "phase2_brand",
        ),
    ],
)
def test_json_question_bank_enforces_ids_sequence_and_phase_membership(
    tmp_path,
    document,
    violation,
):
    with pytest.raises(ManagedQuestionBatchError, match=violation):
        stage_managed_question_batch(
            json.dumps(document, ensure_ascii=False).encode("utf-8"),
            filename="questions.json",
            run_id=f"run-{violation}",
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )
