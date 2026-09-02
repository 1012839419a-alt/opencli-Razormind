import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[2]


def run_resolver(
    engine: str | None, overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if engine is not None:
        env["BROWSER_ENGINE"] = engine
    if overrides:
        env.update(overrides)
    command = ["node", str(ROOT / "scripts" / "resolve-browser-executable.mjs")]
    if engine is not None:
        command.append(engine)
    return subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
    )


def test_resolver_accepts_stock_chromium():
    result = run_resolver("chromium")
    assert result.returncode == 0
    assert result.stdout.strip() == "chromium"


def test_resolver_uses_existing_cloak_binary(tmp_path):
    binary = tmp_path / "cloak"
    binary.write_bytes(b"binary")
    binary.chmod(0o755)
    result = run_resolver("cloakbrowser", {"CLOAKBROWSER_BINARY_PATH": str(binary)})
    assert result.returncode == 0
    assert result.stdout.strip() == str(binary)


def test_resolver_rejects_cloak_directory(tmp_path):
    binary_directory = tmp_path / "cloak"
    binary_directory.mkdir()
    result = run_resolver(
        "cloakbrowser", {"CLOAKBROWSER_BINARY_PATH": str(binary_directory)}
    )
    assert result.returncode != 0
    assert result.stdout == ""


def test_resolver_rejects_unknown_engine():
    result = run_resolver("webkit")
    assert result.returncode != 0
    assert "webkit" in result.stderr



def test_resolver_rejects_empty_environment_engine():
    result = run_resolver(None, {"BROWSER_ENGINE": ""})
    assert result.returncode != 0
    assert result.stdout == ""


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


def _read_entrypoint(name: str) -> str:
    return (ROOT / name / "entrypoint.sh").read_text(encoding="utf-8")


def _start_chrome_body(entrypoint: str) -> str:
    match = re.search(
        r"start_chrome\(\)\s*\{(?P<body>.*?)\n[ \t]*\}", entrypoint, re.DOTALL
    )
    assert match is not None
    return match.group("body")


def test_entrypoints_resolve_browser_engine_with_shared_resolver():
    for name in ("chrome", "agent"):
        entrypoint = _read_entrypoint(name)
        assert 'BROWSER_ENGINE="${BROWSER_ENGINE-chromium}"' in entrypoint
        assert 'BROWSER_ENGINE="${BROWSER_ENGINE:-chromium}"' not in entrypoint
        assert (
            'CHROME_BIN="$(node /usr/local/bin/resolve-browser-executable.mjs '
            '"$BROWSER_ENGINE")" || {'
        ) in entrypoint


def test_agent_resolver_is_gated_by_embedded_chrome_flag():
    entrypoint = _read_entrypoint("agent")
    assert (
        'if [ "${AGENT_HAS_CHROME:-false}" = "true" ]; then HAVE_CHROME=true; fi'
        in entrypoint
    )
    embedded_branch = entrypoint.index('if [ "$HAVE_CHROME" = "true" ]; then')
    resolver_call = entrypoint.index(
        "node /usr/local/bin/resolve-browser-executable.mjs", embedded_branch
    )
    host_branch = entrypoint.index("\nelse\n", embedded_branch)
    assert embedded_branch < resolver_call < host_branch


def test_entrypoints_start_chrome_with_resolved_binary_and_cdp_port():
    for name in ("chrome", "agent"):
        body = _start_chrome_body(_read_entrypoint(name))
        assert '"$CHROME_BIN" --remote-debugging-port=9222' in body
        assert not re.search(r"^\s*chromium(?:\s|$)", body, re.MULTILINE)


def test_entrypoints_do_not_interpolate_license_key_in_logs():
    for name in ("chrome", "agent"):
        for line in _read_entrypoint(name).splitlines():
            if re.search(r"\b(?:echo|printf)\b", line):
                assert "CLOAKBROWSER_LICENSE_KEY" not in line
