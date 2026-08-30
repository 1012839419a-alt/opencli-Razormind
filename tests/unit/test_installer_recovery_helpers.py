import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from backend.security.local_auth import (
    hash_password,
    initialize_password_hash,
    persist_password_hash,
)

ROOT = Path(__file__).resolve().parents[2]


def bash_executable() -> str:
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        shutil.which("bash"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    pytest.skip("A native Bash executable is unavailable.")


def run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [bash_executable(), "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def powershell_executable() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if not executable:
        pytest.skip("PowerShell is unavailable.")
    return executable


def run_powershell(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [powershell_executable(), "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def local_auth_validation_code(path: str) -> str:
    script = (ROOT / path).read_text(encoding="utf-8")
    if path.endswith(".sh"):
        anchor = 'docker exec "$api_id" python -c \''
        terminator = "' || return 1"
    else:
        anchor = "docker exec $ApiId python -c '"
        terminator = "'\n"
    start = script.index(anchor) + len(anchor)
    return script[start : script.index(terminator, start)]


def test_embedded_auth_validation_allows_password_change_and_rejects_bad_marker(
    tmp_path: Path,
) -> None:
    unix_code = local_auth_validation_code("scripts/install-recovery.sh")
    assert unix_code == local_auth_validation_code("scripts/install-recovery.ps1")
    state_path = tmp_path / "local-admin-password.hash"
    initialize_password_hash(hash_password("initial-password"), str(state_path))
    runnable_code = unix_code.replace(
        '"/data/local-admin-password.hash"', json.dumps(str(state_path))
    )

    initial = subprocess.run(
        [sys.executable, "-c", runnable_code], cwd=ROOT, capture_output=True, check=False
    )
    assert initial.returncode == 0, initial.stderr.decode()
    assert initial.stdout == b""

    persist_password_hash(hash_password("legitimate-new-password"), str(state_path))
    changed = subprocess.run(
        [sys.executable, "-c", runnable_code], cwd=ROOT, capture_output=True, check=False
    )
    assert changed.returncode == 0, changed.stderr.decode()
    assert changed.stdout == b""

    state_path.with_name(f"{state_path.name}.initialized").write_text(
        "unsupported-marker\n", encoding="utf-8"
    )
    invalid = subprocess.run(
        [sys.executable, "-c", runnable_code], cwd=ROOT, capture_output=True, check=False
    )
    assert invalid.returncode != 0

    state_path.with_name(f"{state_path.name}.initialized").write_text(
        "opencli-local-auth-state-v1:changed\n", encoding="utf-8"
    )
    state_path.write_text("not-a-password-hash\n", encoding="utf-8")
    malformed = subprocess.run(
        [sys.executable, "-c", runnable_code], cwd=ROOT, capture_output=True, check=False
    )
    assert malformed.returncode != 0
    assert b"not-a-password-hash" not in malformed.stdout + malformed.stderr


def test_unix_helper_classifies_native_default_context_and_quotes_output() -> None:
    result = run_bash(
        r"""
set -eu
. scripts/install-recovery.sh
opencli_is_wsl() { return 1; }
uname() { printf 'Linux\n'; }
docker() { [ "$1 $2 ${3:-}" = "context show " ] && printf 'default\n'; }
systemctl() { [ "$1 $2" = "is-enabled docker" ]; }
unset DOCKER_HOST
opencli_docker_boot_prerequisite_verified
path="/tmp/OpenCLI folder/it's-here"
quoted="$(opencli_shell_quote "$path")"
eval "set -- $quoted"
[ "$1" = "$path" ]
opencli_print_restart_status "$path" 3010 8031 1
"""
    )
    assert result.returncode == 0, result.stderr
    assert "Restart prerequisite verified" in result.stdout
    assert "'/tmp/OpenCLI folder/it'\"'\"'s-here'" in result.stdout
    assert "--verify-restart-recovery" in result.stdout


def test_unix_helper_rejects_wsl_and_propagates_unhealthy_container_failure() -> None:
    result = run_bash(
        r"""
set -eu
. scripts/install-recovery.sh
opencli_is_wsl() { return 0; }
uname() { printf 'Linux\n'; }
docker() {
  case "$*" in
    "compose ps -q api") printf 'api-id\n' ;;
    "inspect --format {{.State.Status}} api-id") printf 'exited\n' ;;
    *) return 1 ;;
  esac
}
systemctl() { return 0; }
if opencli_docker_boot_prerequisite_verified; then exit 10; fi
if opencli_assert_recovered_container api; then exit 11; fi
"""
    )
    assert result.returncode == 0, result.stderr


def test_unix_helper_accepts_current_auth_state_and_propagates_validation_failure() -> None:
    result = run_bash(
        r"""
set -eu
. scripts/install-recovery.sh
auth_validation_status=0
docker() {
  [ "$1 $2" = "exec api-id" ] || return 2
  return "$auth_validation_status"
}
opencli_assert_valid_local_auth_state api-id
auth_validation_status=1
if opencli_assert_valid_local_auth_state api-id; then exit 12; fi
"""
    )
    assert result.returncode == 0, result.stderr


def test_powershell_helper_classifies_windows_and_quotes_output() -> None:
    helper = (ROOT / "scripts" / "install-recovery.ps1").as_posix().replace("'", "''")
    result = run_powershell(
        rf"""
$ErrorActionPreference = 'Stop'
. '{helper}'
if (Test-OpenCliDockerBootPrerequisite) {{ throw 'Windows was misclassified as verified.' }}
$output = (& {{
  Write-OpenCliRestartStatus `
    -Directory "C:\OpenCLI\O'Brien" `
    -FrontendPort 3010 `
    -ApiPort 8031 `
    -BaselineReady $true
}} 3>&1 6>&1 | Out-String)
if ($output -notmatch "O''Brien") {{ throw 'Install path was not safely single-quoted.' }}
if ($output -notmatch 'VerifyRestartRecovery') {{ throw 'Verification command was not printed.' }}
"""
    )
    assert result.returncode == 0, result.stderr


def test_powershell_helper_propagates_container_health_failure() -> None:
    helper = (ROOT / "scripts" / "install-recovery.ps1").as_posix().replace("'", "''")
    result = run_powershell(
        rf"""
$ErrorActionPreference = 'Stop'
. '{helper}'
function docker {{
  if ($args -join ' ' -eq 'compose ps -q api') {{ $global:LASTEXITCODE = 0; return 'api-id' }}
  if (
    $args[0] -eq 'inspect' -and
    $args[-1] -eq 'api-id'
  ) {{ $global:LASTEXITCODE = 0; return 'exited' }}
  $global:LASTEXITCODE = 1
}}
$failed = $false
try {{ Get-OpenCliRecoveredContainer 'api' | Out-Null }} catch {{ $failed = $true }}
if (-not $failed) {{ throw 'Unhealthy container failure did not propagate.' }}
"""
    )
    assert result.returncode == 0, result.stderr


def test_powershell_helper_accepts_current_auth_state_and_propagates_validation_failure() -> None:
    helper = (ROOT / "scripts" / "install-recovery.ps1").as_posix().replace("'", "''")
    result = run_powershell(
        rf"""
$ErrorActionPreference = 'Stop'
. '{helper}'
$script:authValidationExitCode = 0
function docker {{ $global:LASTEXITCODE = $script:authValidationExitCode }}
Test-OpenCliLocalAuthState 'api-id'
$script:authValidationExitCode = 1
$failed = $false
try {{ Test-OpenCliLocalAuthState 'api-id' }} catch {{ $failed = $true }}
if (-not $failed) {{ throw 'Invalid durable auth state did not propagate.' }}
"""
    )
    assert result.returncode == 0, result.stderr
