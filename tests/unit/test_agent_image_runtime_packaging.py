import subprocess

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_agent_image_packages_runtime_adapter_modules():
    dockerfile = (ROOT / "agent" / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY backend/agent_server.py ./backend/agent_server.py" in dockerfile
    assert "COPY backend/agent_runtimes/ ./backend/agent_runtimes/" in dockerfile
    assert "COPY backend/miniflow/ ./backend/miniflow/" in dockerfile


def test_public_images_package_opencli_without_a_private_checkout():
    main_image = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    chrome_image = (ROOT / "chrome" / "Dockerfile").read_text(encoding="utf-8")
    agent_image = (ROOT / "agent" / "Dockerfile").read_text(encoding="utf-8")

    for dockerfile in (main_image, chrome_image, agent_image):
        assert "ARG OPENCLI_VERSION=1.8.7" in dockerfile
        assert "npm install -g @jackwener/opencli@${OPENCLI_VERSION}" in dockerfile
        assert "node /tmp/patch-opencli.js" in dockerfile
        assert "2233admin/OhMyOpenCLI" not in dockerfile
        assert "git clone ${OHMYOPENCLI_REPO}" not in dockerfile

def test_browser_images_package_the_pinned_violentmonkey_bundle_with_notices():
    chrome_image = (ROOT / "chrome" / "Dockerfile").read_text(encoding="utf-8")
    agent_image = (ROOT / "agent" / "Dockerfile").read_text(encoding="utf-8")

    for dockerfile in (chrome_image, agent_image):
        assert (
            "https://github.com/violentmonkey/violentmonkey/releases/download/"
            "v2.48.0/Violentmonkey-mv3-v2.48.0.zip"
        ) in dockerfile
        assert (
            "583ac595bb698a926eadb6064431fce1108dc2f2adb966ed984738824d2d5a54"
        ) in dockerfile
        assert "sha256sum -c -" in dockerfile
        assert (
            "f996dce5391963ed6badd93ad9e2ce2f957b2ad4e587112ea63b1f26317dfb57"
        ) in dockerfile
        assert "extensions/violentmonkey/LICENSE-MIT.txt" in dockerfile
        assert "LICENSE_SOURCE_URL" in dockerfile
        assert "https://github.com/violentmonkey/violentmonkey/tree/v2.48.0" in dockerfile


def test_pinned_violentmonkey_checksum_rejects_a_tampered_archive(tmp_path):
    archive = tmp_path / "Violentmonkey-mv3-v2.48.0.zip"
    archive.write_bytes(b"tampered")

    result = subprocess.run(
        ["sha256sum", "-c", "-"],
        capture_output=True,
        check=False,
        input=(
            "583ac595bb698a926eadb6064431fce1108dc2f2adb966ed984738824d2d5a54  "
            f"{archive}\n"
        ),
        text=True,
    )

    assert result.returncode != 0

def test_browser_entrypoints_start_the_opencli_1_8_7_daemon_module():
    chrome_entrypoint = (ROOT / "chrome" / "entrypoint.sh").read_text(encoding="utf-8")
    agent_entrypoint = (ROOT / "agent" / "entrypoint.sh").read_text(encoding="utf-8")

    for entrypoint in (chrome_entrypoint, agent_entrypoint):
        assert "@jackwener/opencli/dist/src/daemon.js" in entrypoint



def test_browser_images_fail_closed_until_userscripts_access_is_verified():
    chrome_image = (ROOT / "chrome" / "Dockerfile").read_text(encoding="utf-8")
    agent_image = (ROOT / "agent" / "Dockerfile").read_text(encoding="utf-8")
    chrome_entrypoint = (ROOT / "chrome" / "entrypoint.sh").read_text(encoding="utf-8")
    agent_entrypoint = (ROOT / "agent" / "entrypoint.sh").read_text(encoding="utf-8")

    for dockerfile in (chrome_image, agent_image):
        assert (
            "COPY scripts/ensure-violentmonkey-userscripts-access.mjs "
            "/usr/local/bin/ensure-violentmonkey-userscripts-access.mjs"
        ) in dockerfile
        assert "opencli-default/1/extensions/opencli-browser-bridge" in dockerfile
        assert "opencli-default/1/extensions/opencli-script-host" in dockerfile
    for entrypoint in (chrome_entrypoint, agent_entrypoint):
        assert "ensure-violentmonkey-userscripts-access.mjs" in entrypoint
        assert "violentmonkey_user_scripts_access" in entrypoint
        assert 'VIOLENTMONKEY_VERSION="$(read_manifest_component_version violentmonkey)"' in entrypoint
        assert "rm -f /tmp/browser-runtime-report.json" in entrypoint


def test_compose_and_native_start_use_the_opencli_v2_contract():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    native_start = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert compose.count("opencli-default/2/manifest.json") == 2
    assert "opencli-default/1/manifest.json" not in compose
    assert "npm install -g @jackwener/opencli@1.8.7" in native_start
def test_native_adapter_pack_install_requires_an_explicit_repository():
    windows = (ROOT / "scripts" / "install-managed-opencli.ps1").read_text(
        encoding="utf-8"
    )
    linux = (ROOT / "scripts" / "install-agent.sh").read_text(encoding="utf-8")

    assert '[string]$OhMyOpenCliRepo,' in windows
    assert "2233admin/OhMyOpenCLI" not in windows
    assert 'OHMYOPENCLI_REPO="${OHMYOPENCLI_REPO:-}"' in linux
    assert 'if [[ -n "$OHMYOPENCLI_REPO" ]]; then' in linux


def test_anonymous_agent_profiles_are_fresh_per_agent_start():
    entrypoint = (ROOT / "agent" / "entrypoint.sh").read_text(encoding="utf-8")
    installer = (ROOT / "scripts" / "install-agent.sh").read_text(encoding="utf-8")

    assert 'OPENCLI_BROWSER_PROFILE_KIND:-authenticated' in entrypoint
    assert "mktemp -d /tmp/opencli-anonymous-profile.XXXXXX" in entrypoint
    assert 'OPENCLI_BROWSER_PROFILE_KIND" == "anonymous"' in installer
    assert "mktemp -d /tmp/opencli-anonymous-profile.XXXXXX" in installer
