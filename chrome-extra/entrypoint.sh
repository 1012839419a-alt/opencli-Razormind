#!/bin/bash
set -e

# Clean up stale display lock (left by container restart)
rm -f /tmp/.X99-lock

# Start virtual display
Xvfb :99 -screen 0 1280x900x24 -nolisten tcp -extension MIT-SHM &
export DISPLAY=:99

sleep 1

# Remove stale profile locks (left by crashed/restarted containers)
find /home/chrome/.config/chromium -name 'SingletonLock' -o -name 'SingletonCookie' -o -name 'SingletonSocket' 2>/dev/null | xargs rm -f 2>/dev/null || true

# Generate nginx config with this container's hostname so CDP WebSocket URLs
# are rewritten to the correct container name (supports multi-instance pools).
export CHROME_HOSTNAME="${CHROME_HOSTNAME:-${HOSTNAME:-chrome}}"
envsubst '${CHROME_HOSTNAME}' \
  < /etc/nginx/conf.d/cdp.conf.template \
  > /etc/nginx/conf.d/cdp.conf

# nginx proxy: rewrites Host header to localhost so Chrome accepts CDP requests
nginx -g 'daemon off;' &

# Start noVNC web UI on port 6080
# -- quality 9 (max JPEG quality) so captcha text/sliders are crisp for manual solving
#    noVNC default is quality=6 which smudges small text
#    (vnc.html/vnc_auto.html patched below from 6->9 since /usr/share/novnc is read-only)
sed -i 's/type="range" min="0" max="9" value="6"/type="range" min="0" max="9" value="9"/' \
  /usr/share/novnc/vnc.html /usr/share/novnc/vnc_auto.html 2>/dev/null || true
# x11vnc: wait for X to be ready, then start with retry loop.
#   -noshm + -visual TrueColor:32 required: Xvfb has MIT-SHM disabled (container /dev/shm
#   issue causes BadAccess crashes), and x11vnc 0.9.16 exits if XShm is missing without -noshm.
#   NOTE: do NOT pass -quality (removed/obsolete in 0.9.16, breaks arg parsing); noVNC
#   quality is set on the web side (vnc.html patched to 9 below).
(
  for i in $(seq 1 15); do
    x11vnc -display :99 -nopw -listen 0.0.0.0 -xkb -forever -shared -noshm -visual TrueColor:32 >/tmp/x11vnc.log 2>&1 &
    XVNC_PID=$!
    sleep 3
    if kill -0 $XVNC_PID 2>/dev/null; then
      echo "[entrypoint] x11vnc started (pid $XVNC_PID)"
      wait $XVNC_PID
      echo "[entrypoint] x11vnc exited, restarting..."
    else
      echo "[entrypoint] x11vnc failed to start (attempt $i), retrying..."
    fi
    sleep 2
  done
) &
websockify --web /usr/share/novnc 6080 localhost:5900 &

# Captcha alert watchdog: polls doubao tabs via CDP (agent-1:19222); when a
# captcha iframe appears, activates the tab + writes /tmp/CAPTCHA_ALERT so the
# human (noVNC) and drivers know to pause for manual solving.
# Note: runs inside the API container (has python3 + websockets lib); the script
# lives at /tmp/captcha_alert.py there (copied by deploy) or chrome-extra source.
if command -v docker >/dev/null 2>&1; then
  # we're in a container that can reach the api container? usually agent-1 can't.
  # watchdog is deployed to the api container separately; nothing to do here.
  :
fi

# Start Browser Bridge daemon (always enabled).
# Listens on 0.0.0.0 so the API/worker containers can reach it via chrome-{N}:19825.
# The extension connects to ws://localhost:19825/ext.
DAEMON_JS="$(npm root -g)/@jackwener/opencli/dist/daemon.js"
if [ -f "$DAEMON_JS" ]; then
  (while true; do
    OPENCLI_DAEMON_LISTEN=0.0.0.0 node "$DAEMON_JS"
    echo "[entrypoint] Browser Bridge daemon exited, restarting in 1s..."
    sleep 1
  done) &
  echo "[entrypoint] Browser Bridge daemon started on 0.0.0.0:${OPENCLI_DAEMON_PORT:-19825}"
else
  echo "[entrypoint] WARNING: Browser Bridge daemon not found at $DAEMON_JS"
fi

# Keep Chromium running; restart on crash
CHROME_EXTRA_FLAGS=""
if [ -f /home/chrome/extension/manifest.json ]; then
  CHROME_EXTRA_FLAGS="--load-extension=/home/chrome/extension,/home/chrome/tampermonkey"
  echo "[entrypoint] Browser Bridge extension loaded from /home/chrome/extension"
fi

# 2026-08-10 gjx: enable software WebGL (SwiftShader) so Three.js backgrounds
# (e.g. opencli-admin frontend login page) render instead of crashing.
# Without this, the login page throws "THREE.WebGLRenderer: Error creating
# WebGL context" and Next.js shows the global error boundary.
# Note: --use-gl=angle --use-angle=swiftshader caused Chrome to hang on
# startup (DevTools port 9222 never bound); --enable-unsafe-swiftshader
# alone lets Chromium pick SwiftShader for WebGL without forcing GL.
CHROME_EXTRA_FLAGS="$CHROME_EXTRA_FLAGS --enable-unsafe-swiftshader --ignore-gpu-blocklist"

start_chrome() {
  find /home/chrome/.config/chromium -name 'SingletonLock' -o -name 'SingletonCookie' -o -name 'SingletonSocket' 2>/dev/null | xargs rm -f 2>/dev/null || true
  chromium \
    --remote-debugging-port=9222 \
    --remote-debugging-address=0.0.0.0 \
    --remote-allow-origins='*' \
    --no-sandbox \
    --disable-dev-shm-usage \
    --user-data-dir=/home/chrome/.config/chromium \
    --profile-directory=Default-gjx2 \
    --disable-extensions-except=/home/chrome/extension,/home/chrome/tampermonkey \
    --window-size=1280,900 \
    $CHROME_EXTRA_FLAGS \
    "$@"
}

while true; do
  start_chrome || true
  echo "[entrypoint] Chromium exited, restarting in 2s..."
  sleep 2
done
