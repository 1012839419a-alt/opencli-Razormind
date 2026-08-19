from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_release_has_a_runnable_frontend_and_safe_compose_defaults() -> None:
    compose = source("docker-compose.yml")
    frontend_config = source("frontend/next.config.mjs")

    assert "\n  frontend:\n" in compose
    assert "\n  agent-1:\n" in compose
    assert "opencli-admin-frontend:${IMAGE_TAG:-0.4.0}" in compose
    assert "opencli-admin-chrome:${IMAGE_TAG:-0.4.0}" in compose
    assert '"127.0.0.1:${NOVNC_PORT:-6080}:6080"' in compose
    assert "CHROME_IMAGE:" in compose
    assert "./backend:/app/backend" not in compose
    assert "${INVOKEAI_ATTESTED_IMAGE:?" not in compose
    assert "${API_AUTH_TOKEN:?" in compose
    assert "${BOOTSTRAP_ADMIN_TOKEN:?" in compose
    assert "DEVICE_CLAIM_CODE: ${DEVICE_CLAIM_CODE:-}" in compose
    assert "LOCAL_SESSION_COOKIE_SECURE: ${LOCAL_SESSION_COOKIE_SECURE:-false}" in compose
    assert 'output: "standalone"' in frontend_config
    assert (ROOT / "frontend" / "Dockerfile").is_file()


def test_public_release_has_one_ci_frontend_job_and_installers() -> None:
    workflow = source(".github/workflows/ci.yml")
    release_workflow = source(".github/workflows/release.yml")
    windows_installer = source("scripts/install.ps1")
    unix_installer = source("scripts/install.sh")

    assert workflow.count("\n  frontend:\n") == 1
    assert (ROOT / "scripts" / "install.sh").is_file()
    assert (ROOT / "scripts" / "install.ps1").is_file()
    assert (ROOT / ".env.docker.example").is_file()
    assert "BOOTSTRAP_ADMIN_TOKEN" in source(".env.docker.example")
    assert "DEVICE_CLAIM_CODE" in source(".env.docker.example")
    assert "LOCAL_SESSION_COOKIE_SECURE=false" in source(".env.docker.example")
    assert "BOOTSTRAP_ADMIN_TOKEN" in unix_installer
    assert "BOOTSTRAP_ADMIN_TOKEN" in windows_installer
    assert "2233admin/opencli-Razormind" in unix_installer
    assert "2233admin/opencli-Razormind" in windows_installer
    assert "0123456789ABCDEFGHJKMNPQRSTVWXYZ" in unix_installer
    assert "0123456789ABCDEFGHJKMNPQRSTVWXYZ" in windows_installer
    assert "replace_env DEVICE_CLAIM_CODE" in unix_installer
    assert 'Set-EnvValue "DEVICE_CLAIM_CODE"' in windows_installer
    assert "Device claim code:" in unix_installer
    assert "Device claim code:" in windows_installer
    assert "printf 'BOOTSTRAP_ADMIN_TOKEN: %s" not in unix_installer
    assert "printf 'API_AUTH_TOKEN: %s" not in unix_installer
    assert 'Write-Host "BOOTSTRAP_ADMIN_TOKEN:' not in windows_installer
    assert 'Write-Host "API_AUTH_TOKEN:' not in windows_installer
    assert 'os.environ.get("NOVNC_BASE_PORT", 6080)' in source(
        "backend/api/v1/browsers.py"
    )
    assert "Assert-NativeSuccess" in windows_installer
    assert "-UseBasicParsing" in windows_installer
    assert "http://localhost:$frontendPort/login" in windows_installer
    assert 'raw="$(openssl rand -base64 32)" || return 1' in unix_installer
    assert 'if [ -z "$credential_encryption_key" ]; then' in unix_installer
    assert "packages: write" in release_workflow
    assert "id-token: write" not in release_workflow


def test_nas_reference_has_current_version_and_visible_secret_sentinels() -> None:
    nas_env = source(".env.nas.example")
    values = dict(
        line.split("=", 1)
        for line in nas_env.splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    assert values["IMAGE_TAG"] == "0.4.0"
    assert values["LOCAL_SESSION_COOKIE_SECURE"] == "false"
    for key in (
        "API_AUTH_TOKEN",
        "BOOTSTRAP_ADMIN_TOKEN",
        "DEVICE_CLAIM_CODE",
        "SECRET_KEY",
        "CREDENTIAL_ENCRYPTION_KEY",
        "POSTGRES_PASSWORD",
    ):
        assert values[key]
    assert len(values["DEVICE_CLAIM_CODE"]) == 10
    assert set(values["DEVICE_CLAIM_CODE"]) <= set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
    assert "opencli_secret" not in values["POSTGRES_PASSWORD"]
    assert "change-me-in-production" not in nas_env
    assert "不是家庭设备默认栈" in nas_env


def test_readme_leads_with_local_device_claim_and_keeps_oidc_optional() -> None:
    readme = source("README.md")

    assert "一次性设备认领码" in readme
    assert "创建本地管理员" in readme
    assert "OIDC 是可选的组织登录方式" in readme
    assert "不会把值打印到终端" in readme
