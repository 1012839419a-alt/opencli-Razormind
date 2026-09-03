#!/usr/bin/env node

import { fileURLToPath } from "node:url";

const endpoint = (process.argv[2] ?? "http://localhost:9222").replace(/\/$/, "");
const violentmonkeyVersion = process.argv[3];
const cdpTimeoutMs = 5_000;
const targetTimeoutMs = 10_000;

function localWebSocketUrl(rawUrl) {
  const source = new URL(rawUrl);
  const target = new URL(endpoint);
  source.hostname = target.hostname;
  source.port = target.port;
  return source.toString();
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function fetchJson(path) {
  let response;
  try {
    response = await fetch(`${endpoint}${path}`, {
      signal: AbortSignal.timeout(cdpTimeoutMs),
    });
  } catch (error) {
    throw new Error(`CDP ${path} request failed: ${error.message}`);
  }
  if (!response.ok) {
    throw new Error(`CDP ${path} returned ${response.status}`);
  }
  return response.json();
}

function cdp(webSocketUrl, method, params = {}) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(localWebSocketUrl(webSocketUrl));
    const timeout = setTimeout(() => {
      socket.close();
      reject(new Error(`${method} timed out`));
    }, cdpTimeoutMs);
    socket.addEventListener("open", () => {
      socket.send(JSON.stringify({ id: 1, method, params }));
    });
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id !== 1) return;
      clearTimeout(timeout);
      socket.close();
      if (message.error) {
        reject(new Error(`${method} failed: ${message.error.message ?? "unknown CDP error"}`));
        return;
      }
      resolve(message.result ?? {});
    });
    socket.addEventListener("error", () => {
      clearTimeout(timeout);
      reject(new Error(`${method} websocket failed`));
    });
  });
}

async function evaluate(webSocketUrl, expression) {
  const result = await cdp(webSocketUrl, "Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(
      `Runtime.evaluate failed: ${result.exceptionDetails.exception?.description ?? result.exceptionDetails.text ?? "unknown exception"}`,
    );
  }
  return result.result?.value;
}

async function createTarget(browserWebSocketUrl, url) {
  const result = await cdp(browserWebSocketUrl, "Target.createTarget", {
    url,
    background: true,
  });
  if (!result.targetId) {
    throw new Error(`Target.createTarget did not return a target ID for ${url}`);
  }
  return result.targetId;
}

async function closeTarget(browserWebSocketUrl, targetId) {
  await cdp(browserWebSocketUrl, "Target.closeTarget", { targetId });
}

async function targetById(targetId) {
  const deadline = Date.now() + targetTimeoutMs;
  while (Date.now() < deadline) {
    const targets = await fetchJson("/json/list");
    const target = targets.find(
      (candidate) => candidate.id === targetId && candidate.type === "page" && candidate.webSocketDebuggerUrl,
    );
    if (target) return target;
    await sleep(100);
  }
  throw new Error(`CDP target ${targetId} did not become debuggable`);
}

async function findViolentmonkeyWorker() {
  const targets = await fetchJson("/json/list");
  for (const target of targets) {
    if (
      target.type !== "service_worker" ||
      !target.url?.startsWith("chrome-extension://") ||
      !target.webSocketDebuggerUrl
    ) {
      continue;
    }
    try {
      const manifest = await evaluate(
        target.webSocketDebuggerUrl,
        "(() => { const manifest = chrome.runtime.getManifest(); return { id: chrome.runtime.id, name: manifest.name, version: manifest.version }; })()",
      );
      const extensionId = new URL(target.url).hostname;
      if (
        manifest?.id === extensionId &&
        manifest.name === "Violentmonkey" &&
        manifest.version === violentmonkeyVersion
      ) {
        return { extensionId, target };
      }
    } catch {
      // Extensions can terminate while the bundle is still starting. The caller retries.
    }
  }
  throw new Error(`Violentmonkey ${violentmonkeyVersion} service worker was not found`);
}

function developerPrivateExpression(extensionId) {
  return `
    (async () => {
      const api = globalThis.chrome?.developerPrivate;
      if (!api) throw new Error("chrome.developerPrivate is unavailable in chrome://extensions");
      const findExtension = async () => {
        const extensions = await api.getExtensionsInfo({ includeDisabled: true, includeTerminated: true });
        return extensions.find((extension) => extension.id === ${JSON.stringify(extensionId)});
      };
      let extension = await findExtension();
      if (!extension) throw new Error("Violentmonkey is absent from chrome.developerPrivate");
      if (!extension.userScriptsAccess?.isActive) {
        await api.updateExtensionConfiguration({
          extensionId: ${JSON.stringify(extensionId)},
          userScriptsAccess: true,
        });
        extension = await findExtension();
      }
      const access = extension?.userScriptsAccess;
      if (!access?.isEnabled || !access?.isActive) {
        throw new Error("Violentmonkey userScriptsAccess is not active: " + JSON.stringify(access));
      }
      return { isEnabled: access.isEnabled, isActive: access.isActive };
    })()
  `;
}

function ownCommandExpression(command, data) {
  return `
    (async () => {
      const controller =
        navigator.serviceWorker.controller || (await navigator.serviceWorker.ready).active;
      if (!controller) throw new Error("Violentmonkey service worker does not control its options page");
      const id = crypto.randomUUID();
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          navigator.serviceWorker.removeEventListener("message", onMessage);
          reject(new Error("Violentmonkey command ${command} timed out"));
        }, 5_000);
        const onMessage = (event) => {
          if (event.data?.id !== id) return;
          clearTimeout(timeout);
          navigator.serviceWorker.removeEventListener("message", onMessage);
          if (event.data.err) {
            reject(new Error(event.data.err.message || String(event.data.err)));
          } else {
            resolve(event.data.res);
          }
        };
        navigator.serviceWorker.addEventListener("message", onMessage);
        controller.postMessage({ id, msg: ${JSON.stringify({ cmd: command, data })} });
      });
    })()
  `;
}

function probeSource(marker, probeUrl) {
  return `// ==UserScript==
// @name         noVNC userScriptsAccess startup probe ${marker}
// @namespace    opencli-novnc-runtime-self-check
// @version      1.0.0
// @match        ${probeUrl}
// @run-at       document-start
// @grant        none
// ==/UserScript==

document.documentElement.setAttribute("data-novnc-vm-probe", ${JSON.stringify(marker)});
`;
}

async function waitForExtensionRuntime(pageWebSocketUrl) {
  const deadline = Date.now() + targetTimeoutMs;
  while (Date.now() < deadline) {
    try {
      if (
        (await evaluate(
          pageWebSocketUrl,
          "typeof globalThis.chrome?.runtime?.sendMessage",
        )) === "function"
      ) {
        return;
      }
    } catch {
      // The target exists before its extension page finishes initializing.
    }
    await sleep(100);
  }
  throw new Error("Violentmonkey options page did not initialize its extension runtime");
}

async function waitForProbe(pageWebSocketUrl, marker) {
  const deadline = Date.now() + targetTimeoutMs;
  while (Date.now() < deadline) {
    const observed = await evaluate(
      pageWebSocketUrl,
      'document.documentElement?.getAttribute("data-novnc-vm-probe")',
    );
    if (observed === marker) return;
    await sleep(100);
  }
  throw new Error("Violentmonkey user script did not execute on the probe page");
}

async function verifyUserScriptExecution(browserWebSocketUrl, extensionId, probeUrl) {
  const optionsTargetId = await createTarget(
    browserWebSocketUrl,
    `chrome-extension://${extensionId}/options/index.html`,
  );
  let optionsTarget;
  let probeTargetId;
  let probeScriptId;
  try {
    optionsTarget = await targetById(optionsTargetId);
    await waitForExtensionRuntime(optionsTarget.webSocketDebuggerUrl);
    const marker = `novnc-vm-${crypto.randomUUID()}`;
    const parsed = await evaluate(
      optionsTarget.webSocketDebuggerUrl,
      ownCommandExpression("ParseScript", { code: probeSource(marker, probeUrl) }),
    );
    probeScriptId = parsed?.where?.id;
    if (!Number.isInteger(probeScriptId)) {
      throw new Error("Violentmonkey did not return an ID for the probe user script");
    }

    probeTargetId = await createTarget(browserWebSocketUrl, probeUrl);
    const probeTarget = await targetById(probeTargetId);
    await waitForProbe(probeTarget.webSocketDebuggerUrl, marker);
    return { executed: true };
  } finally {
    if (probeScriptId !== undefined && optionsTarget) {
      await Promise.allSettled([
        evaluate(
          optionsTarget.webSocketDebuggerUrl,
          ownCommandExpression("UpdateScriptInfo", {
            id: probeScriptId,
            config: { removed: 1 },
          }),
        ),
      ]);
      await Promise.allSettled([
        evaluate(
          optionsTarget.webSocketDebuggerUrl,
          ownCommandExpression("RemoveScripts", [probeScriptId]),
        ),
      ]);
    }
    await Promise.allSettled([
      ...(probeTargetId
        ? [closeTarget(browserWebSocketUrl, probeTargetId)]
        : []),
      closeTarget(browserWebSocketUrl, optionsTargetId),
    ]);
  }
}

export async function ensureViolentmonkeyUserScriptsAccess() {
  if (!violentmonkeyVersion) {
    throw new Error("expected Violentmonkey version is required");
  }
  const [version, { extensionId }] = await Promise.all([
    fetchJson("/json/version"),
    findViolentmonkeyWorker(),
  ]);
  if (!version.webSocketDebuggerUrl) {
    throw new Error("CDP browser websocket URL is missing");
  }

  const extensionsTargetId = await createTarget(
    version.webSocketDebuggerUrl,
    "chrome://extensions/",
  );
  let access;
  try {
    const extensionsTarget = await targetById(extensionsTargetId);
    access = await evaluate(
      extensionsTarget.webSocketDebuggerUrl,
      developerPrivateExpression(extensionId),
    );
  } finally {
    await closeTarget(version.webSocketDebuggerUrl, extensionsTargetId);
  }

  const probeUrl = new URL("/json/version", `${endpoint}/`).toString();
  const probe = await verifyUserScriptExecution(
    version.webSocketDebuggerUrl,
    extensionId,
    probeUrl,
  );
  return {
    ok: true,
    extension: { id: extensionId, version: violentmonkeyVersion },
    userScriptsAccess: access,
    probe,
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    process.stdout.write(`${JSON.stringify(await ensureViolentmonkeyUserScriptsAccess())}\n`);
  } catch (error) {
    process.stderr.write(`[ensure-violentmonkey-userscripts-access] ${error.message}\n`);
    process.exitCode = 1;
  }
}
