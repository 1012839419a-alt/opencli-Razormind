"""Validate the repository's pinned InvokeAI upstream governance metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PINNED_COMMIT = "d315b8967f548732912bd9b390853ed4af97d8cb"
OPENAPI_SHA256 = "2793f48c5b3b31cb849e7afcfa204c7f47d834bc5a684fdb06481c06f7befac1"
IMAGE_PATTERN = re.compile(r"^ghcr\.io/invoke-ai/invokeai@sha256:[0-9a-f]{64}$")
REQUIRED_GOVERNANCE_FILES = ("NOTICE.md", "source-files.json", "PATCHES.md")
ADR_PATH = Path("docs/adr/0026-invokeai-canvas-is-an-audited-first-party-subeditor.md")


def check(root: Path) -> list[str]:
    manifest_path = root / "docs" / "vendor" / "invokeai" / "upstream.json"
    if not manifest_path.is_file():
        return [f"missing InvokeAI upstream manifest: {manifest_path}"]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid InvokeAI upstream manifest: {exc}"]

    commit = manifest.get("commit")
    image = manifest.get("container_image")
    errors: list[str] = []
    if commit == "latest" or (isinstance(image, str) and ":latest" in image):
        errors.append(
            "floating InvokeAI references are forbidden; pin commit and image digest"
        )
    if commit != PINNED_COMMIT:
        errors.append(f"InvokeAI commit must be pinned to {PINNED_COMMIT}")
    if manifest.get("license") != "Apache-2.0":
        errors.append("InvokeAI license must be Apache-2.0")
    if not isinstance(image, str) or IMAGE_PATTERN.fullmatch(image) is None:
        errors.append("InvokeAI container image must use a ghcr.io sha256 digest")
    if manifest.get("openapi_sha256") != OPENAPI_SHA256:
        errors.append(f"InvokeAI OpenAPI SHA-256 must be {OPENAPI_SHA256}")
    if manifest.get("custom_node_installation") != "disabled":
        errors.append("InvokeAI custom node installation must remain disabled")
    vendor_dir = manifest_path.parent
    for filename in REQUIRED_GOVERNANCE_FILES:
        if not (vendor_dir / filename).is_file():
            errors.append(f"missing InvokeAI governance file: {filename}")
    if not (root / ADR_PATH).is_file():
        errors.append(f"missing InvokeAI first-party subeditor ADR: {ADR_PATH}")

    inventory_path = vendor_dir / "source-files.json"
    if inventory_path.is_file():
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            vendored_root = root / inventory["vendored_root"]
            registered = set(inventory["files"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            errors.append(f"invalid InvokeAI source inventory: {exc}")
        else:
            if vendored_root.is_dir():
                actual = {
                    path.relative_to(vendored_root).as_posix()
                    for path in vendored_root.rglob("*")
                    if path.is_file()
                }
                for relative_path in sorted(actual - registered):
                    errors.append(f"unexplained vendored file: {relative_path}")
                for relative_path in sorted(registered - actual):
                    errors.append(f"registered vendored file is missing: {relative_path}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    errors = check(args.root.resolve())
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("InvokeAI upstream contract is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
