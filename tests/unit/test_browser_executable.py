import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[2]


def run_resolver(
    engine: str, overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["BROWSER_ENGINE"] = engine
    if overrides:
        env.update(overrides)
    return subprocess.run(
        ["node", str(ROOT / "scripts" / "resolve-browser-executable.mjs"), engine],
        env=env,
        capture_output=True,
        text=True,
    )


def test_resolver_accepts_stock_chromium():
    result = run_resolver("chromium")
    assert result.stdout.strip() == "chromium"


def test_resolver_uses_existing_cloak_binary(tmp_path):
    binary = tmp_path / "cloak"
    binary.write_bytes(b"binary")
    result = run_resolver("cloakbrowser", {"CLOAKBROWSER_BINARY_PATH": str(binary)})
    assert result.stdout.strip() == str(binary)


def test_resolver_rejects_unknown_engine():
    result = run_resolver("webkit")
    assert result.returncode != 0
    assert "webkit" in result.stderr


def test_resolver_rejects_empty_engine():
    result = run_resolver("")
    assert result.returncode != 0
    assert result.stdout == ""


def test_resolver_does_not_fallback_when_override_missing(tmp_path):
    result = run_resolver(
        "cloakbrowser",
        {"CLOAKBROWSER_BINARY_PATH": str(tmp_path / "missing")},
    )
    assert result.returncode != 0
    assert "fallback" not in result.stderr.lower()
