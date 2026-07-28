from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_invokeai_upstream.py"
PINNED_COMMIT = "d315b8967f548732912bd9b390853ed4af97d8cb"
OPENAPI_SHA256 = "2793f48c5b3b31cb849e7afcfa204c7f47d834bc5a684fdb06481c06f7befac1"


def _run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_manifest(root: Path, **overrides: object) -> None:
    vendor_dir = root / "docs" / "vendor" / "invokeai"
    vendor_dir.mkdir(parents=True)
    manifest = {
        "name": "InvokeAI",
        "repository": "https://github.com/invoke-ai/InvokeAI",
        "commit": PINNED_COMMIT,
        "license": "Apache-2.0",
        "container_image": "ghcr.io/invoke-ai/invokeai@sha256:" + "1" * 64,
        "openapi_sha256": OPENAPI_SHA256,
        "custom_node_installation": "disabled",
    }
    manifest.update(overrides)
    (vendor_dir / "upstream.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def _write_governance_files(root: Path, *, files: list[str] | None = None) -> None:
    vendor_dir = root / "docs" / "vendor" / "invokeai"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    (vendor_dir / "NOTICE.md").write_text("InvokeAI notice\n", encoding="utf-8")
    (vendor_dir / "PATCHES.md").write_text("InvokeAI patch ledger\n", encoding="utf-8")
    (vendor_dir / "source-files.json").write_text(
        json.dumps(
            {
                "vendored_root": "frontend/features/image-studio/invokeai",
                "files": files or [],
            }
        ),
        encoding="utf-8",
    )


def test_checker_rejects_a_floating_invokeai_reference(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        commit="latest",
        container_image="ghcr.io/invoke-ai/invokeai:latest",
    )

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "floating" in result.stderr.lower()


def test_checker_requires_the_approved_invokeai_commit(tmp_path: Path) -> None:
    _write_manifest(tmp_path, commit="a" * 40)

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert PINNED_COMMIT in result.stderr


def test_checker_enforces_license_digest_openapi_and_custom_node_policy(
    tmp_path: Path,
) -> None:
    invalid_values = [
        ("license", "MIT", "Apache-2.0"),
        ("container_image", "ghcr.io/invoke-ai/invokeai:6.13.7", "digest"),
        ("openapi_sha256", "0" * 64, OPENAPI_SHA256),
        ("custom_node_installation", "enabled", "disabled"),
    ]

    for field, value, expected_message in invalid_values:
        case_root = tmp_path / field
        _write_manifest(case_root, **{field: value})

        result = _run_checker(case_root)

        assert result.returncode == 1, field
        assert expected_message in result.stderr, field


def test_checker_requires_notice_source_inventory_and_patch_ledger(tmp_path: Path) -> None:
    _write_manifest(tmp_path)

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "NOTICE.md" in result.stderr
    assert "source-files.json" in result.stderr
    assert "PATCHES.md" in result.stderr


def test_checker_rejects_an_unexplained_vendored_source_file(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    _write_governance_files(tmp_path)
    unexpected = (
        tmp_path
        / "frontend"
        / "features"
        / "image-studio"
        / "invokeai"
        / "Canvas.tsx"
    )
    unexpected.parent.mkdir(parents=True)
    unexpected.write_text("export const Canvas = () => null\n", encoding="utf-8")

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "unexplained vendored file" in result.stderr.lower()
    assert "Canvas.tsx" in result.stderr


def test_checker_requires_the_first_party_subeditor_adr(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    _write_governance_files(tmp_path)

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "first-party subeditor ADR" in result.stderr


def test_repository_invokeai_governance_contract_is_complete() -> None:
    result = _run_checker(REPO_ROOT)

    assert result.returncode == 0, result.stderr
    assert "valid" in result.stdout.lower()
