"""Recover Doubao recommended follow-ups from preserved bottom screenshots.

The tool is deliberately two-phase: without ``--apply`` it only writes an OCR
report; with ``--apply`` it atomically updates records whose follow-up chips are
unambiguous.  It never opens Doubao or submits a search.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from backend.workflow.gaojixing_doubao_driver import (
    _brand_observation,
    _inline_followups,
)

_TRAILING_ARROW = re.compile(r"\s*(?:→|➡|➜|›|>|》)\s*$")


def _bottom_screenshot(run_root: Path, record: dict[str, Any]) -> Path:
    evidence = record.get("page_evidence")
    files = evidence.get("screenshot_files") if isinstance(evidence, dict) else None
    if not isinstance(files, list) or not files:
        raise ValueError("screenshot_files_missing")
    names = [str(item) for item in files]
    bottom = [item for item in names if "底部" in Path(item).name]
    relative = bottom[-1] if bottom else names[-1]
    path = (run_root / relative).resolve()
    if run_root.resolve() not in path.parents or not path.is_file():
        raise ValueError("bottom_screenshot_missing")
    return path


def _recover_followups(
    image_path: Path, engine: RapidOCR
) -> tuple[list[str], list[dict[str, Any]]]:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        width, height = image.size
        # The left fifth is Doubao's conversation sidebar; the bottom 8% is the
        # composer.  Keeping the full vertical answer range avoids assuming a
        # fixed number or position of chips.
        crop = image.crop((int(width * 0.20), 0, width, int(height * 0.92)))
    rows, _elapsed = engine(np.asarray(crop))
    details: list[dict[str, Any]] = []
    recovered: list[str] = []
    for row in rows or []:
        if not isinstance(row, list) or len(row) < 3:
            continue
        text = re.sub(r"\s+", " ", str(row[1] or "")).strip()
        confidence = float(row[2] or 0)
        if not _TRAILING_ARROW.search(text):
            continue
        text = _TRAILING_ARROW.sub("", text).strip()
        if not (4 < len(text) < 160 and text.endswith(("?", "？"))):
            continue
        details.append({"text": text, "confidence": round(confidence, 6)})
        if text not in recovered:
            recovered.append(text)
    return recovered, details


def _write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _apply_followups(path: Path, record: dict[str, Any], followups: list[str]) -> None:
    modules = record["page_modules"]
    evidence = record["page_evidence"]
    expectations = evidence["module_expectations"]
    modules["followups"] = followups
    expectations["followups"] = {
        "displayed": True,
        "expected_count": len(followups),
    }
    missing = record.get("required_missing")
    if isinstance(missing, list):
        record["required_missing"] = [
            item for item in missing if item != "recommended-followups-missing"
        ]
    record["brand_observation"] = _brand_observation(
        str(record.get("question") or ""),
        str(record.get("answer") or ""),
        modules,
    )
    _write_json_atomic(path, record)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--only-id", action="append", default=[])
    args = parser.parse_args()

    run_root = args.run_root.resolve()
    raw_root = run_root / "raw"
    engine = RapidOCR()
    rows: list[dict[str, Any]] = []
    applied = 0
    raw_files = sorted(raw_root.glob("*.json"))
    if args.only_id:
        selected = set(args.only_id)
        raw_files = [path for path in raw_files if path.stem in selected]
    for index, path in enumerate(raw_files, start=1):
        record = json.loads(path.read_text(encoding="utf-8"))
        entry: dict[str, Any] = {
            "id": record.get("id"),
            "question": record.get("question"),
            "rawFile": path.name,
        }
        try:
            screenshot = _bottom_screenshot(run_root, record)
            followups, details = _recover_followups(screenshot, engine)
            recovery_mode = "chips"
            if not followups:
                followups = _inline_followups(record.get("answer"))
                recovery_mode = "inline-invitation"
            confidence = min(
                (item["confidence"] for item in details), default=0.0
            )
            certain = bool(followups) and (
                recovery_mode == "inline-invitation" or confidence >= 0.88
            )
            entry.update(
                {
                    "bottomScreenshot": screenshot.relative_to(run_root).as_posix(),
                    "followups": followups,
                    "count": len(followups),
                    "minConfidence": confidence,
                    "recoveryMode": recovery_mode,
                    "status": "certain" if certain else "review",
                }
            )
            if args.apply and certain:
                _apply_followups(path, record, followups)
                applied += 1
        except Exception as exc:  # noqa: BLE001 - report every damaged record
            entry.update({"followups": [], "count": 0, "status": "error", "error": str(exc)})
        rows.append(entry)
        if index % 10 == 0 or index == len(raw_files):
            print(f"processed {index}/{len(raw_files)}", flush=True)

    summary = {
        "records": len(rows),
        "certain": sum(item["status"] == "certain" for item in rows),
        "review": sum(item["status"] == "review" for item in rows),
        "errors": sum(item["status"] == "error" for item in rows),
        "applied": applied,
        "followupCount": sum(int(item["count"]) for item in rows),
    }
    _write_json_atomic(args.report, {"summary": summary, "records": rows})
    print(json.dumps(summary, ensure_ascii=True), flush=True)
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
