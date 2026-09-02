#!/usr/bin/env node

const endpoint = (process.argv[2] ?? "http://localhost:9222").replace(/\/$/, "");

function localWebSocketUrl(rawUrl) {
  const source = new URL(rawUrl);
  const target = new URL(endpoint);
  source.hostname = target.hostname;
  source.port = target.port;
  return source.toString();
}

function evaluate(webSocketUrl, expression, id = 1) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(localWebSocketUrl(webSocketUrl));
    const timeout = setTimeout(() => {
      socket.close();
      reject(new Error("CDP evaluation timed out"));
    }, 5000);
    socket.addEventListener("open", () => {
      socket.send(
        JSON.stringify({
          id,
          method: "Runtime.evaluate",
          params: { expression, returnByValue: true },
        }),
      );
    });
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id !== id) return;
      clearTimeout(timeout);
      socket.close();
      if (message.error || message.result?.exceptionDetails) {
        reject(new Error("CDP evaluation failed"));
        return;
      }
      resolve(message.result?.result?.value);
    });
    socket.addEventListener("error", () => {
      clearTimeout(timeout);
      reject(new Error("CDP websocket failed"));
    });
  });
}

async function createBackgroundTarget(webSocketUrl, url) {
  await new Promise((resolve, reject) => {
    const socket = new WebSocket(localWebSocketUrl(webSocketUrl));
    const timeout = setTimeout(() => {
      socket.close();
      reject(new Error("Target.createTarget timed out"));
    }, 5000);
    socket.addEventListener("open", () => {
      socket.send(
        JSON.stringify({
          id: 1,
          method: "Target.createTarget",
          params: { url, background: true },
        }),
      );
    });
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id !== 1) return;
      clearTimeout(timeout);
      socket.close();
      if (message.error || !message.result?.targetId) {
        reject(new Error(message.error?.message ?? "Target.createTarget failed"));
        return;
      }
      resolve(message.result.targetId);
    });
    socket.addEventListener("error", () => {
      clearTimeout(timeout);
      reject(new Error("browser CDP websocket failed"));
    });
  });
}

const [targetsResponse, versionResponse] = await Promise.all([
  fetch(`${endpoint}/json/list`),
  fetch(`${endpoint}/json/version`),
]);
if (!targetsResponse.ok || !versionResponse.ok) process.exit(1);
const targets = await targetsResponse.json();
const version = await versionResponse.json();
let hostUrl = null;
for (const target of targets) {
  if (
    target.type !== "service_worker" ||
    !target.url?.startsWith("chrome-extension://") ||
    !target.webSocketDebuggerUrl
  ) {
    continue;
  }
  try {
    const name = await evaluate(
      target.webSocketDebuggerUrl,
      "chrome.runtime.getManifest().name",
    );
    if (name === "OpenCLI Script Host") {
      hostUrl = new URL("host.html", target.url).toString();
      break;
    }
  } catch {
    // Another extension can disappear while targets are being inspected.
  }
}
if (!hostUrl) process.exit(2);
if (targets.some((target) => target.type === "page" && target.url === hostUrl)) {
  process.stdout.write(hostUrl);
  process.exit(0);
}
await createBackgroundTarget(version.webSocketDebuggerUrl, hostUrl);
process.stdout.write(hostUrl);
