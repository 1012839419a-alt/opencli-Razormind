ARG REGISTRY=
FROM ${REGISTRY}node:22-bookworm-slim AS browser-bridge-extension

ARG BBX_EXTENSION_REPOSITORY=https://github.com/koltyakov/browser-bridge.git
ARG BBX_EXTENSION_COMMIT=5d9ab7993abef13ace6a893b58b0a333f5fb2e61

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git openssl zip \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 "${BBX_EXTENSION_REPOSITORY}" /src/browser-bridge \
    && cd /src/browser-bridge \
    && git fetch --depth 1 origin "${BBX_EXTENSION_COMMIT}" \
    && git checkout "${BBX_EXTENSION_COMMIT}" \
    && node scripts/package-extension.mjs

COPY agent/inject-extension-key.mjs /tmp/inject-extension-key.mjs
COPY agent/headless-auto-enable.js /tmp/headless-auto-enable.js
COPY agent/patch-browser-bridge-autostart.mjs /tmp/patch-browser-bridge-autostart.mjs
RUN openssl genrsa -out /tmp/browser-bridge-extension-key.pem 2048 \
    && openssl rsa -in /tmp/browser-bridge-extension-key.pem -pubout -outform DER \
       -out /tmp/browser-bridge-extension-public.der 2>/dev/null \
    && node /tmp/inject-extension-key.mjs \
       /src/browser-bridge/dist/browser-bridge-extension/manifest.json \
       /tmp/browser-bridge-extension-public.der \
       /src/browser-bridge/dist/browser-bridge-extension-id \
    && node /tmp/patch-browser-bridge-autostart.mjs \
       /src/browser-bridge/dist/browser-bridge-extension/packages/extension/src/background.js \
       /tmp/headless-auto-enable.js \
       /src/browser-bridge/dist/browser-bridge-extension/packages/extension/src/headless-auto-enable.js

FROM ${REGISTRY}python:3.13-slim

ARG INSTALL_CHROME=false
ARG BBX_VERSION=1.11.1

# Base system deps (always installed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git procps \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && if ! command -v npm >/dev/null 2>&1; then \
        apt-get install -y --no-install-recommends npm; \
    fi \
    && rm -rf /var/lib/apt/lists/*

# ── Optional: Chromium + VNC + virtual display ────────────────────────────────
# Set INSTALL_CHROME=true at build time to embed Chrome in the image.
# Default: false — connect to Chrome running on the host machine instead.
# With Chrome:    ~1.2 GB image, self-contained (no host Chrome required)
# Without Chrome: ~200 MB image, host provides Chrome via OPENCLI_CDP_ENDPOINT
RUN if [ "$INSTALL_CHROME" = "true" ]; then \
    apt-get update && apt-get install -y --no-install-recommends \
        chromium xvfb fonts-noto-cjk x11vnc novnc websockify nginx gettext-base \
    && rm -rf /var/lib/apt/lists/*; \
fi

# Install both browser runtimes globally. OpenCLI remains available for the
# legacy collect path; BBX is the workflow-native Browser Bridge runtime.
ARG OPENCLI_VERSION=1.8.5
COPY scripts/patch-opencli.js /tmp/patch-opencli.js
RUN npm install -g @jackwener/opencli@${OPENCLI_VERSION} @browserbridge/bbx@${BBX_VERSION} \
    && node /tmp/patch-opencli.js \
    && rm /tmp/patch-opencli.js \
    && rm -rf /root/.npm

# Python deps for agent_server only — intentionally minimal
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    httpx \
    pyyaml \
    websockets

# Official Browser Bridge extension. The build pins the upstream source and
# injects a stable key so the native-messaging allowlist matches this unpacked
# extension on every container start.
COPY --from=browser-bridge-extension /src/browser-bridge/dist/browser-bridge-extension/ /home/agent/extension/
COPY --from=browser-bridge-extension /src/browser-bridge/dist/browser-bridge-extension-id /etc/browser-bridge-extension-id
COPY chrome/nginx-cdp.conf.template /home/agent/nginx-cdp.conf.template

# Keep the existing OpenCLI browser extension available for the legacy bridge
# collect path. It is loaded alongside BBX in the unified profile.
COPY chrome/extension-src/ /home/agent/opencli-extension/

# Agent server source plus the runtime adapters it imports at startup.
WORKDIR /app
COPY backend/agent_server.py ./backend/agent_server.py
COPY backend/agent_runtimes/ ./backend/agent_runtimes/
COPY backend/miniflow/ ./backend/miniflow/
COPY backend/security/ ./backend/security/
RUN touch ./backend/__init__.py

COPY agent/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

RUN useradd -m -u 1000 agent \
    && mkdir -p /home/agent/.config/chromium \
    && if [ "$INSTALL_CHROME" = "true" ]; then \
        mkdir -p /etc/nginx/conf.d /var/lib/nginx /var/log/nginx /run \
        && rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true \
        && sed -i 's/user www-data;//' /etc/nginx/nginx.conf \
        && sed -i 's|pid /run/nginx.pid|pid /tmp/nginx.pid|' /etc/nginx/nginx.conf \
        && chown -R agent:agent /etc/nginx /var/lib/nginx /var/log/nginx /run; \
    fi \
    && chown -R agent:agent /home/agent /app

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # MiniFlow executes only workflows packaged under this allowlisted root.
    MINIFLOW_WORKFLOW_ROOT=/app/workflows \
    # Bridge daemon port (used when Chrome is embedded OR daemon runs on host)
    OPENCLI_DAEMON_PORT=19825 \
    # Browser Bridge native host transport stays loopback-only inside the VNC agent.
    BBX_TCP_PORT=19826 \
    BBX_TCP_HOST=127.0.0.1 \
    BBX_TCP_BIND_HOST=127.0.0.1 \
    # Baked at build time so agent_server knows whether Chrome is bundled.
    # true  → connect to container-local Chrome (localhost)
    # false → connect to host Chrome (host.docker.internal)
    AGENT_HAS_CHROME=${INSTALL_CHROME}

USER agent

# Unified VNC Agent ports: noVNC, CDP proxy, Agent WS/HTTP, and legacy OpenCLI.
EXPOSE 6080 19222 19823 19825

ENTRYPOINT ["/entrypoint.sh"]
