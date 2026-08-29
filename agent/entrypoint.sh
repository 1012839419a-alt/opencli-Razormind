#!/bin/bash
set -e

# Detect whether Chrome is embedded in this image.
# If not, agent_server connects to the host-provided Chrome via env vars.
HAVE_CHROME=false
if command -v chromium > /dev/null 2>&1; then
    HAVE_CHROME=true
fi

# Runtime files are read-only and versioned outside the writable browser
# profile. Required components fail startup instead of silently dropping
# capabilities.
BROWSER_RUNTIME_BUNDLE_ROOT="${BROWSER_RUNTIME_BUNDLE_ROOT:-/opt/browser-runtime-bundles}"
BROWSER_RUNTIME_BUNDLE_MANIFEST="${BROWSER_RUNTIME_BUNDLE_MANIFEST:-$BROWSER_RUNTIME_BUNDLE_ROOT/opencli-default/1/manifest.json}"
BUNDLE_EXTENSION_OUTPUT="$(
    node /usr/local/bin/resolve-browser-runtime-bundle.mjs \
        "$BROWSER_RUNTIME_BUNDLE_MANIFEST" \
        "$BROWSER_RUNTIME_BUNDLE_ROOT"
)"
BUNDLE_RUNTIME_REPORT="$(
    node /usr/local/bin/resolve-browser-runtime-bundle.mjs \
        "$BROWSER_RUNTIME_BUNDLE_MANIFEST" \
        "$BROWSER_RUNTIME_BUNDLE_ROOT" \
        --report
)"
SCRIPT_HOST_ENABLED="$(
    node -e 'const manifest=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8")); process.stdout.write(String(manifest.components.some((component)=>component.id==="opencli-script-host")));' \
        "$BROWSER_RUNTIME_BUNDLE_MANIFEST"
)"
BUNDLE_EXTENSION_DIRS=()
if [ -n "$BUNDLE_EXTENSION_OUTPUT" ]; then
    mapfile -t BUNDLE_EXTENSION_DIRS <<< "$BUNDLE_EXTENSION_OUTPUT"
fi
CHROME_EXTRA_FLAGS=(--disable-extensions)
if [ "${#BUNDLE_EXTENSION_DIRS[@]}" -gt 0 ]; then
    EXTENSION_DIRS="$(IFS=,; echo "${BUNDLE_EXTENSION_DIRS[*]}")"
    CHROME_EXTRA_FLAGS=(
        "--disable-extensions-except=$EXTENSION_DIRS"
        "--load-extension=$EXTENSION_DIRS"
    )
    echo "[agent] Runtime bundle loaded from $BROWSER_RUNTIME_BUNDLE_MANIFEST"
fi
NETWORK_MODE="$(
    node -e 'const policy=JSON.parse(process.argv[1]||"{\"mode\":\"direct\"}"); if(!["direct","restricted"].includes(policy.mode)) process.exit(1); process.stdout.write(policy.mode);' \
        "${BROWSER_NETWORK_POLICY:-}"
)"
if [ "$NETWORK_MODE" = "restricted" ]; then
    CHROME_EXTRA_FLAGS+=("--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost")
fi
STARTUP_PAGES=()
if [ -n "${BROWSER_STARTUP_PAGES:-}" ]; then
    STARTUP_PAGE_OUTPUT="$(
        node -e 'const pages=JSON.parse(process.argv[1]); if(!Array.isArray(pages)||pages.length>10||pages.some((item)=>typeof item!=="string"||!/^https?:\/\//.test(item))) process.exit(1); process.stdout.write(pages.join("\n"));' \
            "$BROWSER_STARTUP_PAGES"
    )"
    if [ -n "$STARTUP_PAGE_OUTPUT" ]; then
        mapfile -t STARTUP_PAGES <<< "$STARTUP_PAGE_OUTPUT"
    fi
fi


if [ "$HAVE_CHROME" = "true" ]; then
    export OPENCLI_CDP_ENDPOINT="http://localhost:9222"
    echo "[agent] Chrome detected — starting embedded browser stack"

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

    # ── 3. Browser Bridge daemon (for bridge mode) ────────────────────────────
    DAEMON_JS="$(npm root -g)/@jackwener/opencli/dist/daemon.js"
    if [ -f "$DAEMON_JS" ]; then
        (while true; do
            OPENCLI_DAEMON_LISTEN=127.0.0.1 node "$DAEMON_JS"
            echo "[agent] Bridge daemon exited, restarting in 1s..."
            sleep 1
        done) &
        echo "[agent] Bridge daemon started on 127.0.0.1:${OPENCLI_DAEMON_PORT:-19825}"
    else
        echo "[agent] WARNING: Bridge daemon not found at $DAEMON_JS"
    fi

    # ── 4. Chrome ─────────────────────────────────────────────────────────────
    start_chrome() {
        find "$CHROME_PROFILE" \
            -name 'SingletonLock' -o -name 'SingletonCookie' -o -name 'SingletonSocket' \
            2>/dev/null | xargs rm -f 2>/dev/null || true
        chromium \
            --remote-debugging-port=9222 \
            --remote-debugging-address=127.0.0.1 \
            --remote-allow-origins='*' \
            --no-sandbox \
            --disable-dev-shm-usage \
            --user-data-dir="$CHROME_PROFILE" \
            "${CHROME_EXTRA_FLAGS[@]}" \
            "$@"
    }

    (while true; do
        start_chrome "${STARTUP_PAGES[@]}" || true
        echo "[agent] Chrome exited, restarting in 2s..."
        sleep 2
    done) &

    # ── 5. Wait for Chrome CDP ────────────────────────────────────────────────
    echo "[agent] Waiting for Chrome CDP..."
    CHROME_READY=false
    for i in $(seq 1 30); do
        if curl -sf http://localhost:9222/json/version > /dev/null 2>&1; then
            EXTENSION_WORKERS="$(
                curl -sf http://localhost:9222/json/list |
                    node -e 'let data=""; process.stdin.on("data",(chunk)=>data+=chunk); process.stdin.on("end",()=>{const targets=JSON.parse(data); process.stdout.write(String(targets.filter((target)=>target.type==="service_worker"&&target.url.startsWith("chrome-extension://")).length));});'
            )"
            if [ "$EXTENSION_WORKERS" -ge "${#BUNDLE_EXTENSION_DIRS[@]}" ]; then
                if [ "$SCRIPT_HOST_ENABLED" != "true" ] ||
                    node /usr/local/bin/ensure-script-host.mjs http://localhost:9222 >/dev/null; then
                    CHROME_READY=true
                    echo "[agent] Chrome runtime ready"
                    break
                fi
            fi
        fi
        sleep 1
    done
    if [ "$CHROME_READY" = "true" ]; then
        printf '%s\n' "$BUNDLE_RUNTIME_REPORT" > /tmp/browser-runtime-report.json
    else
        echo "[agent] Chrome did not become ready; runtime report not written" >&2
    fi

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
