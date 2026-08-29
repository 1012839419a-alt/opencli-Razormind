ARG REGISTRY=
FROM ${REGISTRY}python:3.13-slim

# Base system deps (always installed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git procps \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Optional: headless Chrome + virtual display ───────────────────────────────
# Set INSTALL_CHROME=true at build time to embed Chrome in the image.
# Default: false — connect to Chrome running on the host machine instead.
# With Chrome:    ~1.2 GB image, self-contained (no host Chrome required)
# Without Chrome: ~200 MB image, host provides Chrome via OPENCLI_CDP_ENDPOINT
ARG INSTALL_CHROME=false
RUN if [ "$INSTALL_CHROME" = "true" ]; then \
    apt-get update && apt-get install -y --no-install-recommends \
        chromium xvfb fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*; \
fi

# Install opencli globally — available as 'opencli' on PATH
ARG OPENCLI_VERSION=1.8.5
COPY scripts/patch-opencli.js /tmp/patch-opencli.js
RUN npm install -g @jackwener/opencli@${OPENCLI_VERSION} \
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

# Default bundle is immutable image content. Browser profiles only store site
# state and can be mounted independently without changing capabilities.
COPY chrome/runtime-bundles/ /opt/browser-runtime-bundles/
COPY chrome/extension-src/manifest.json /opt/browser-runtime-bundles/opencli-default/1/extensions/opencli-browser-bridge/manifest.json
COPY chrome/extension-src/icons/ /opt/browser-runtime-bundles/opencli-default/1/extensions/opencli-browser-bridge/icons/
COPY chrome/extension-src/dist/background.js /opt/browser-runtime-bundles/opencli-default/1/extensions/opencli-browser-bridge/dist/background.js
COPY chrome/script-host/ /opt/browser-runtime-bundles/opencli-default/1/extensions/opencli-script-host/
COPY scripts/resolve-browser-runtime-bundle.mjs /usr/local/bin/resolve-browser-runtime-bundle.mjs
COPY scripts/ensure-script-host.mjs /usr/local/bin/ensure-script-host.mjs

# Agent server source plus the runtime adapters it imports at startup.
WORKDIR /app
COPY backend/agent_server.py ./backend/agent_server.py
COPY backend/agent_runtime_dispatch.py ./backend/agent_runtime_dispatch.py
COPY backend/agent_runtimes/ ./backend/agent_runtimes/
COPY backend/miniflow/ ./backend/miniflow/
COPY backend/security/ ./backend/security/
RUN touch ./backend/__init__.py

COPY agent/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

RUN useradd -m -u 1000 agent \
    && mkdir -p /home/agent/.config/chromium \
    && chown -R agent:agent /home/agent /app

ARG INSTALL_CHROME=false
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Bridge daemon port (used when Chrome is embedded OR daemon runs on host)
    OPENCLI_DAEMON_PORT=19825 \
    # Baked at build time so agent_server knows whether Chrome is bundled.
    # true  → connect to container-local Chrome (localhost)
    # false → connect to host Chrome (host.docker.internal)
    AGENT_HAS_CHROME=${INSTALL_CHROME}

USER agent

# agent_server HTTP port
EXPOSE 19823

ENTRYPOINT ["/entrypoint.sh"]
