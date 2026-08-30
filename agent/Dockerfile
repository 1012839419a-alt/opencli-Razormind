ARG REGISTRY=
FROM ${REGISTRY}python:3.13-slim

# Base system deps (always installed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git procps unzip \
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
ARG OPENCLI_VERSION=1.8.7
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
COPY chrome/extension-src/manifest.json /opt/browser-runtime-bundles/opencli-default/2/extensions/opencli-browser-bridge/manifest.json
COPY chrome/extension-src/icons/ /opt/browser-runtime-bundles/opencli-default/2/extensions/opencli-browser-bridge/icons/
COPY chrome/extension-src/dist/background.js /opt/browser-runtime-bundles/opencli-default/2/extensions/opencli-browser-bridge/dist/background.js
COPY chrome/script-host/ /opt/browser-runtime-bundles/opencli-default/2/extensions/opencli-script-host/
RUN set -eux; \
    curl -fsSL -o /tmp/violentmonkey.zip https://github.com/violentmonkey/violentmonkey/releases/download/v2.48.0/Violentmonkey-mv3-v2.48.0.zip; \
    echo "583ac595bb698a926eadb6064431fce1108dc2f2adb966ed984738824d2d5a54  /tmp/violentmonkey.zip" | sha256sum -c -; \
    mkdir -p /opt/browser-runtime-bundles/opencli-default/2/extensions/violentmonkey; \
    unzip -q /tmp/violentmonkey.zip -d /opt/browser-runtime-bundles/opencli-default/2/extensions/violentmonkey; \
    curl -fsSL -o /tmp/violentmonkey-LICENSE https://raw.githubusercontent.com/violentmonkey/violentmonkey/v2.48.0/LICENSE; \
    echo "f996dce5391963ed6badd93ad9e2ce2f957b2ad4e587112ea63b1f26317dfb57  /tmp/violentmonkey-LICENSE" | sha256sum -c -; \
    install -m 0644 /tmp/violentmonkey-LICENSE /opt/browser-runtime-bundles/opencli-default/2/extensions/violentmonkey/LICENSE-MIT.txt; \
    printf '%s\n' https://github.com/violentmonkey/violentmonkey/tree/v2.48.0 > /opt/browser-runtime-bundles/opencli-default/2/extensions/violentmonkey/SOURCE_URL; \
    printf '%s\n' https://raw.githubusercontent.com/violentmonkey/violentmonkey/v2.48.0/LICENSE > /opt/browser-runtime-bundles/opencli-default/2/extensions/violentmonkey/LICENSE_SOURCE_URL; \
    rm /tmp/violentmonkey.zip /tmp/violentmonkey-LICENSE
COPY scripts/resolve-browser-runtime-bundle.mjs /usr/local/bin/resolve-browser-runtime-bundle.mjs
COPY scripts/ensure-script-host.mjs /usr/local/bin/ensure-script-host.mjs
COPY scripts/ensure-violentmonkey-userscripts-access.mjs /usr/local/bin/ensure-violentmonkey-userscripts-access.mjs

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
