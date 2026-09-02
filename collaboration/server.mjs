import { createServer } from "node:http"
import { docs, setupWSConnection } from "@y/websocket-server/utils"
import WebSocket from "ws"
const { Server: WebSocketServer } = WebSocket

const port = parsePort(process.env.PORT ?? "1234")
const apiUrl = requiredUrl(process.env.COLLABORATION_API_URL ?? "http://api:8000")
const apiToken = required("API_AUTH_TOKEN")
const debounceMs = parseBoundedInteger(process.env.SNAPSHOT_DEBOUNCE_MS ?? "250", 100, 10_000)
const maxSnapshotBytes = parseBoundedInteger(
  process.env.MAX_SNAPSHOT_BYTES ?? "1048576",
  1_024,
  10 * 1024 * 1024,
)
const requestTimeoutMs = parseBoundedInteger(process.env.API_REQUEST_TIMEOUT_MS ?? "5000", 100, 30_000)

const websocketServer = new WebSocketServer({ noServer: true, maxPayload: maxSnapshotBytes })
const roomHooks = new WeakSet()
const snapshotTimers = new WeakMap()
const snapshotInFlight = new WeakSet()
const snapshotPending = new WeakSet()

const server = createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://localhost")
  if (request.method === "GET" && url.pathname === "/health") {
    response.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" })
    response.end('{"status":"ok"}')
    return
  }
  response.writeHead(404, { "content-type": "application/json" })
  response.end('{"error":"not found"}')
})

server.on("upgrade", async (request, socket, head) => {
  try {
    const url = new URL(request.url ?? "/", "http://localhost")
    const room = roomFromPath(url.pathname)
    const token = url.searchParams.get("token")
    if (!room || !token) {
      rejectUpgrade(socket, 401, "Unauthorized")
      return
    }

    const authorizedRoom = await authorizeRoom(room, token)
    if (authorizedRoom !== room) {
      rejectUpgrade(socket, 403, "Forbidden")
      return
    }

    websocketServer.handleUpgrade(request, socket, head, (connection) => {
      connection.on("error", () => connection.terminate())
      setupWSConnection(connection, request, { docName: room })
      installSnapshotHook(docs.get(room), room)
    })
  } catch (error) {
    logError("websocket upgrade rejected", error)
    rejectUpgrade(socket, 401, "Unauthorized")
  }
})

function installSnapshotHook(doc, room) {
  if (!doc || roomHooks.has(doc)) return
  roomHooks.add(doc)
  doc.on("update", () => scheduleSnapshot(doc, room))
}

function scheduleSnapshot(doc, room) {
  clearTimeout(snapshotTimers.get(doc))
  snapshotTimers.set(
    doc,
    setTimeout(() => void sendSnapshot(doc, room), debounceMs),
  )
}

async function sendSnapshot(doc, room) {
  snapshotTimers.delete(doc)
  if (snapshotInFlight.has(doc)) {
    snapshotPending.add(doc)
    return
  }
  snapshotInFlight.add(doc)
  try {
    const payload = JSON.stringify({
      room,
      data: {
        nodes: { type: "Map", content: doc.getMap("nodes").toJSON() },
        edges: { type: "Map", content: doc.getMap("edges").toJSON() },
      },
    })
    if (Buffer.byteLength(payload) > maxSnapshotBytes) {
      console.error("collaboration snapshot exceeds configured byte limit", { room })
      return
    }
    const response = await fetch(`${apiUrl}/api/v1/internal/collaboration/snapshot`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${apiToken}`,
        "content-type": "application/json",
      },
      body: payload,
      signal: AbortSignal.timeout(requestTimeoutMs),
    })
    if (!response.ok) {
      console.error("collaboration snapshot rejected", { room, status: response.status })
    }
  } catch (error) {
    logError("collaboration snapshot failed", error)
  } finally {
    snapshotInFlight.delete(doc)
    if (snapshotPending.delete(doc)) scheduleSnapshot(doc, room)
  }
}

async function authorizeRoom(room, token) {
  const response = await fetch(`${apiUrl}/api/v1/internal/collaboration/authorize`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ room }),
    signal: AbortSignal.timeout(requestTimeoutMs),
  })
  if (!response.ok) throw new Error(`authorization status ${response.status}`)
  const body = await response.json()
  const authorizedRoom = body?.data?.room
  if (typeof authorizedRoom !== "string") throw new Error("authorization response is invalid")
  return authorizedRoom
}

function roomFromPath(pathname) {
  if (!pathname.startsWith("/") || pathname.length > 513) return null
  try {
    const room = decodeURIComponent(pathname.slice(1))
    return room.includes("/") || !room ? null : room
  } catch {
    return null
  }
}

function rejectUpgrade(socket, statusCode, reason) {
  if (!socket.writable) return
  socket.write(`HTTP/1.1 ${statusCode} ${reason}\r\nConnection: close\r\n\r\n`)
  socket.destroy()
}

function required(name) {
  const value = process.env[name]?.trim()
  if (!value) throw new Error(`${name} must be configured`)
  return value
}

function requiredUrl(value) {
  const url = new URL(value)
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("COLLABORATION_API_URL must use http or https")
  }
  return url.toString().replace(/\/$/, "")
}

function parsePort(value) {
  return parseBoundedInteger(value, 1, 65_535)
}

function parseBoundedInteger(value, minimum, maximum) {
  const parsed = Number.parseInt(value, 10)
  if (!Number.isSafeInteger(parsed) || String(parsed) !== value || parsed < minimum || parsed > maximum) {
    throw new Error(`Expected an integer from ${minimum} to ${maximum}`)
  }
  return parsed
}

function logError(message, error) {
  console.error(message, {
    message: error instanceof Error ? error.message : String(error),
    stack: error instanceof Error ? error.stack : undefined,
  })
}

server.listen(port, "0.0.0.0", () => {
  console.log(`Studio collaboration service listening on :${port}`)
})
