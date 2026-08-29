from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_agent_image_packages_runtime_adapter_modules():
    dockerfile = (ROOT / "agent" / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY backend/agent_server.py ./backend/agent_server.py" in dockerfile
    assert "COPY backend/agent_runtimes/ ./backend/agent_runtimes/" in dockerfile
    assert "COPY backend/miniflow/ ./backend/miniflow/" in dockerfile

    assert "COPY backend/security/ ./backend/security/" in dockerfile


def test_public_images_package_opencli_without_a_private_checkout():
    main_image = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    agent_image = (ROOT / "agent" / "Dockerfile").read_text(encoding="utf-8")

    for dockerfile in (main_image, agent_image):
        assert "ARG OPENCLI_VERSION=1.8.5" in dockerfile
        assert "npm install -g @jackwener/opencli@${OPENCLI_VERSION}" in dockerfile
        assert "node /tmp/patch-opencli.js" in dockerfile
        assert "2233admin/OhMyOpenCLI" not in dockerfile
        assert "git clone ${OHMYOPENCLI_REPO}" not in dockerfile

    assert "command -v npm" in agent_image


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


def test_vnc_agent_image_is_the_registered_browser_bridge_runtime():
    dockerfile = (ROOT / "agent" / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "agent" / "entrypoint.sh").read_text(encoding="utf-8")
    auto_enable = (ROOT / "agent" / "headless-auto-enable.js").read_text(encoding="utf-8")
    patcher = (ROOT / "agent" / "patch-browser-bridge-autostart.mjs").read_text(
        encoding="utf-8"
    )
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    build = (ROOT / "docker-compose.build.yml").read_text(encoding="utf-8")

    assert "@browserbridge/bbx@${BBX_VERSION}" in dockerfile
    assert "BBX_EXTENSION_COMMIT" in dockerfile
    assert "scripts/package-extension.mjs" in dockerfile
    assert "x11vnc novnc websockify nginx" in dockerfile
    assert "COPY backend/agent_server.py ./backend/agent_server.py" in dockerfile
    assert "bbx install" in entrypoint
    assert "bbx-daemon" in entrypoint
    assert "env -u OPENCLI_DAEMON_PORT" in entrypoint
    assert "--profile-directory=Default" in entrypoint
    assert "--no-first-run" in entrypoint
    assert "patch-browser-bridge-autostart.mjs" in dockerfile
    assert "headless-auto-enable.js" in dockerfile
    assert "autoEnableHeadlessWindow" in auto_enable
    assert "/^https?:\\/\\//i.test(candidate.url)" in auto_enable
    adapter = (ROOT / "backend" / "agent_runtimes" / "bbx_adapter.py").read_text(
        encoding="utf-8"
    )
    assert "conversation-item" in adapter
    assert "initializeState" in patcher
    assert "websockify --web /usr/share/novnc 6080 localhost:5900" in entrypoint
    assert "https://www.doubao.com/chat" in entrypoint
    assert "AGENT_MODE: ${AGENT_MODE:-bridge}" in compose
    assert "AGENT_REGISTER: ${AGENT_REGISTER:-ws}" in compose
    assert "AGENT_ADVERTISE_URL: ${AGENT_ADVERTISE_URL:-http://agent-1:19823}" in compose
    assert "agent_profile_1:/home/agent/.config/chromium" in compose
    assert "${AGENT_PORT:-19823}:19823" in compose
    assert "agent-1:\n    <<: *agent-build" in build
