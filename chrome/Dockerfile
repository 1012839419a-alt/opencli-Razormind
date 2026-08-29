ARG REGISTRY=
FROM ${REGISTRY}debian:bookworm-slim

# OPENCLI_VERSION: pin the opencli release; patch-opencli.js adds DAEMON_HOST/LISTEN env hooks
ARG OPENCLI_VERSION=1.8.5
COPY scripts/patch-opencli.js /tmp/patch-opencli.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium x11vnc xvfb novnc websockify procps nginx \
    fonts-noto-cjk gettext-base \
    curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @jackwener/opencli@${OPENCLI_VERSION} \
    && node /tmp/patch-opencli.js \
    && rm /tmp/patch-opencli.js \
    && rm -rf /root/.npm /var/lib/apt/lists/*

COPY chrome/nginx-cdp.conf.template /etc/nginx/conf.d/cdp.conf.template

RUN useradd -m -u 1000 chrome \
    && rm /etc/nginx/sites-enabled/default 2>/dev/null || true \
    && chown -R chrome:chrome /var/lib/nginx /var/log/nginx /run /etc/nginx/conf.d \
    && sed -i 's/user www-data;//' /etc/nginx/nginx.conf \
    && sed -i 's|pid /run/nginx.pid|pid /tmp/nginx.pid|' /etc/nginx/nginx.conf \
    && mkdir -p /tmp/.X11-unix \
    && chmod 1777 /tmp/.X11-unix \
    && ln -sf /usr/share/novnc/vnc_lite.html /usr/share/novnc/index.html

COPY chrome/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

# Default bundle is immutable image content. Deployments may mount another
# versioned directory read-only, but never place components in the Profile.
COPY chrome/runtime-bundles/ /opt/browser-runtime-bundles/
COPY chrome/extension-src/manifest.json /opt/browser-runtime-bundles/opencli-default/1/extensions/opencli-browser-bridge/manifest.json
COPY chrome/extension-src/icons/ /opt/browser-runtime-bundles/opencli-default/1/extensions/opencli-browser-bridge/icons/
COPY chrome/extension-src/dist/background.js /opt/browser-runtime-bundles/opencli-default/1/extensions/opencli-browser-bridge/dist/background.js
COPY chrome/script-host/ /opt/browser-runtime-bundles/opencli-default/1/extensions/opencli-script-host/
COPY scripts/resolve-browser-runtime-bundle.mjs /usr/local/bin/resolve-browser-runtime-bundle.mjs
COPY scripts/ensure-script-host.mjs /usr/local/bin/ensure-script-host.mjs

EXPOSE 6080 19222 19825

USER chrome
# Pre-create profile directory as chrome user so Docker initialises new
# named volumes with the correct ownership (avoids "Permission denied" on
# first run when a fresh volume is mounted over a root-owned path).
RUN mkdir -p /home/chrome/.config/chromium

ENTRYPOINT ["/entrypoint.sh"]
