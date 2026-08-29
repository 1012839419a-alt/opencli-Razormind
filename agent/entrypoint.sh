#!/bin/bash
set -e

# Detect whether Chrome is embedded in this image.
# If not, agent_server connects to the host-provided Chrome via env vars.
HAVE_CHROME=false
if command -v chromium > /dev/null 2>&1; then
    HAVE_CHROME=true
fi

if [ "$HAVE_CHROME" = "true" ]; then
    echo "[agent] Chrome detected — starting unified VNC + Browser Bridge stack"

    CHROME_PROFILE=/home/agent/.config/chromium
    if [ "${OPENCLI_BROWSER_PROFILE_KIND:-authenticated}" = "anonymous" ]; then
        CHROME_PROFILE="$(mktemp -d /tmp/opencli-anonymous-profile.XXXXXX)"
        echo "[agent] Anonymous profile requested — using fresh $CHROME_PROFILE"
    fi

    # ── 1. Virtual display ────────────────────────────────────────────────────
    rm -f /tmp/.X99-lock
    Xvfb :99 -screen 0 1280x900x24 -nolisten tcp &
    export DISPLAY=:99
    sleep 1

    # ── 2. Clean stale Chrome locks ───────────────────────────────────────────
    find "$CHROME_PROFILE" \
        -name 'SingletonLock' -o -name 'SingletonCookie' -o -name 'SingletonSocket' \
        2>/dev/null | xargs rm -f 2>/dev/null || true

    # ── 3. CDP proxy and noVNC ─────────────────────────────────────────────────
    export CHROME_HOSTNAME="${CHROME_HOSTNAME:-${HOSTNAME:-agent-1}}"
    mkdir -p /etc/nginx/conf.d
    envsubst '${CHROME_HOSTNAME}' \
        < /home/agent/nginx-cdp.conf.template \
        > /etc/nginx/conf.d/cdp.conf
    nginx -g 'daemon off;' &
    x11vnc -display :99 -nopw -listen 0.0.0.0 -xkb -forever -shared &
    websockify --web /usr/share/novnc 6080 localhost:5900 &

    # ── 4. Official Browser Bridge native host + daemon ──────────────────────
    BBX_EXTENSION_ID="$(tr -d '\r\n' < /etc/browser-bridge-extension-id)"
    if [ -n "$BBX_EXTENSION_ID" ]; then
        bbx install "$BBX_EXTENSION_ID" --browser chromium \
            || echo "[agent] WARNING: Browser Bridge native host install failed"
    else
        echo "[agent] WARNING: Browser Bridge extension ID is missing"
    fi
    (while true; do
        bbx-daemon
        echo "[agent] BBX daemon exited, restarting in 1s..."
        sleep 1
    done) &
    echo "[agent] BBX daemon started on ${BBX_TCP_HOST:-127.0.0.1}:${BBX_TCP_PORT:-19826}"

    # ── 5. Legacy OpenCLI bridge daemon ──────────────────────────────────────
    DAEMON_JS="$(npm root -g)/@jackwener/opencli/dist/src/daemon.js"
    if [ -f "$DAEMON_JS" ]; then
        (while true; do
            env -u OPENCLI_DAEMON_PORT OPENCLI_DAEMON_LISTEN=0.0.0.0 node "$DAEMON_JS"
            echo "[agent] Bridge daemon exited, restarting in 1s..."
            sleep 1
        done) &
        echo "[agent] OpenCLI bridge daemon started on 0.0.0.0:${OPENCLI_DAEMON_PORT:-19825}"
    else
        echo "[agent] WARNING: Bridge daemon not found at $DAEMON_JS"
    fi

    # ── 6. Chrome ─────────────────────────────────────────────────────────────
    start_chrome() {
        find "$CHROME_PROFILE" \
            -name 'SingletonLock' -o -name 'SingletonCookie' -o -name 'SingletonSocket' \
            2>/dev/null | xargs rm -f 2>/dev/null || true
        # Keep the authenticated VNC profile warm on the Doubao origin. This
        # gives the patched Browser Bridge extension a normal web tab to
        # authorize automatically after a headless restart.
        if [ "$#" -eq 0 ]; then
            set -- https://www.doubao.com/chat
        fi
        chromium \
            --remote-debugging-port=9222 \
            --remote-debugging-address=127.0.0.1 \
            --remote-allow-origins='*' \
            --no-sandbox \
            --disable-dev-shm-usage \
            --no-first-run \
            --no-default-browser-check \
            --disable-session-crashed-bubble \
            --user-data-dir="$CHROME_PROFILE" \
            --profile-directory=Default \
            --load-extension=/home/agent/extension,/home/agent/opencli-extension \
            --window-size=1280,900 \
            "$@"
    }

    (while true; do
        start_chrome || true
        echo "[agent] Chrome exited, restarting in 2s..."
        sleep 2
    done) &

    # ── 7. Wait for Chrome CDP ────────────────────────────────────────────────
    echo "[agent] Waiting for Chrome CDP..."
    for i in $(seq 1 30); do
        if curl -sf http://localhost:9222/json/version > /dev/null 2>&1; then
            echo "[agent] Chrome ready"
            break
        fi
        sleep 1
    done

else
    echo "[agent] No embedded Chrome — connecting to host Chrome via OPENCLI_CDP_ENDPOINT / OPENCLI_DAEMON_HOST"
    echo "[agent]   CDP endpoint : ${OPENCLI_CDP_ENDPOINT:-<not set>}"
    echo "[agent]   Bridge daemon: ${OPENCLI_DAEMON_HOST:-<not set>}:${OPENCLI_DAEMON_PORT:-19825}"
fi

# ── Agent server ───────────────────────────────────────────────────────────────
exec uvicorn backend.agent_server:app \
    --host 0.0.0.0 \
    --port "${AGENT_PORT:-19823}" \
    --log-level info
