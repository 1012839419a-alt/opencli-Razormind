"use client"

// Thin Yjs wrapper for real-time collaboration on canonical workflow graph
// records plus awareness cursors. The transport remains decoupled from canvas UI.

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import * as Y from "yjs"
import { WebsocketProvider } from "y-websocket"
import { nanoid } from "nanoid"
import { getApiAuthToken } from "@/lib/api/auth-token"

const COLORS = ["#ff7a17", "#4ade80", "#a0c3ec", "#f87171", "#c084fc", "#facc15"]
const NAMES = ["Ada", "Alan", "Grace", "Linus", "Rita", "Ken", "Barbara", "Dennis"]
const LOCAL_ORIGIN = Symbol("workflow-yjs-local")

type CanonicalWorkflowRecord = { id: string }

export interface RemoteCursor {
  id: number
  name: string
  color: string
  x: number
  y: number
}

export interface RemoteUser {
  id: number
  name: string
  color: string
}

export interface YjsBinding {
  authorized: boolean
  connected: boolean
  synced: boolean
  users: RemoteUser[]
  cursors: RemoteCursor[]
  /**
   * Seed an empty room once synchronization completes. A non-empty room wins
   * over this client's loaded draft.
   */
  initialize(nodes: CanonicalWorkflowRecord[], edges: CanonicalWorkflowRecord[]): void
  /** Publish local canonical graph state after the initial room decision. */
  publish(nodes: CanonicalWorkflowRecord[], edges: CanonicalWorkflowRecord[]): void
  /** Publish local cursor position (flow coords). */
  publishCursor(x: number, y: number): void
  /** Subscribe to remote canonical graph updates. */
  onRemote(handler: (nodes: CanonicalWorkflowRecord[], edges: CanonicalWorkflowRecord[]) => void): () => void
}

const NULL_BINDING: YjsBinding = {
  authorized: false,
  connected: false,
  synced: false,
  users: [],
  cursors: [],
  initialize: () => {},
  publish: () => {},
  publishCursor: () => {},
  onRemote: () => () => {},
}

type ProviderBinding = {
  doc: Y.Doc
  provider: WebsocketProvider
  nodesMap: Y.Map<CanonicalWorkflowRecord>
  edgesMap: Y.Map<CanonicalWorkflowRecord>
  initialized: boolean
}

function setRecordIfChanged(
  records: Y.Map<CanonicalWorkflowRecord>,
  record: CanonicalWorkflowRecord,
): void {
  const current = records.get(record.id)
  if (current && JSON.stringify(current) === JSON.stringify(record)) return
  records.set(record.id, record)
}

export function useYjs(
  enabled: boolean,
  { url, room }: { url: string; room: string },
): YjsBinding {
  const token = getApiAuthToken()
  const [connected, setConnected] = useState(false)
  const [synced, setSynced] = useState(false)
  const [users, setUsers] = useState<RemoteUser[]>([])
  const [cursors, setCursors] = useState<RemoteCursor[]>([])
  const remoteHandlerRef = useRef<((nodes: CanonicalWorkflowRecord[], edges: CanonicalWorkflowRecord[]) => void) | null>(null)
  const applyingRemote = useRef(false)

  const identity = useMemo(
    () => ({
      name: NAMES[Math.floor(Math.random() * NAMES.length)] + "-" + nanoid(3),
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
    }),
    [],
  )

  const bindingRef = useRef<ProviderBinding | null>(null)

  const emitRemote = useCallback(() => {
    const binding = bindingRef.current
    const handler = remoteHandlerRef.current
    if (!binding || !handler) return
    applyingRemote.current = true
    handler(Array.from(binding.nodesMap.values()), Array.from(binding.edgesMap.values()))
    queueMicrotask(() => {
      applyingRemote.current = false
    })
  }, [])

  useEffect(() => {
    if (!enabled || !token || typeof window === "undefined") return

    const doc = new Y.Doc()
    const nodesMap = doc.getMap<CanonicalWorkflowRecord>("nodes")
    const edgesMap = doc.getMap<CanonicalWorkflowRecord>("edges")
    const provider = new WebsocketProvider(url, room, doc, { params: { token } })

    provider.awareness.setLocalStateField("user", identity)
    bindingRef.current = { doc, provider, nodesMap, edgesMap, initialized: false }

    const onStatus = ({ status }: { status: "connected" | "disconnected" | "connecting" }) => {
      setConnected(status === "connected")
    }
    const onSync = (state: boolean) => setSynced(state)
    const onNodesUpdate = (_event: Y.YMapEvent<CanonicalWorkflowRecord>, transaction: Y.Transaction) => {
      if (transaction.origin !== LOCAL_ORIGIN) emitRemote()
    }
    const onEdgesUpdate = (_event: Y.YMapEvent<CanonicalWorkflowRecord>, transaction: Y.Transaction) => {
      if (transaction.origin !== LOCAL_ORIGIN) emitRemote()
    }
    const onAwareness = () => {
      const states = Array.from(provider.awareness.getStates().entries())
      const nextUsers: RemoteUser[] = []
      const nextCursors: RemoteCursor[] = []
      const localId = provider.awareness.clientID
      for (const [clientId, state] of states) {
        const current = state as { user?: RemoteUser; cursor?: { x: number; y: number } }
        if (!current.user || clientId === localId) continue
        nextUsers.push({ id: clientId, name: current.user.name, color: current.user.color })
        if (current.cursor) {
          nextCursors.push({
            id: clientId,
            name: current.user.name,
            color: current.user.color,
            x: current.cursor.x,
            y: current.cursor.y,
          })
        }
      }
      setUsers(nextUsers)
      setCursors(nextCursors)
    }

    provider.on("status", onStatus)
    provider.on("sync", onSync)
    nodesMap.observe(onNodesUpdate)
    edgesMap.observe(onEdgesUpdate)
    provider.awareness.on("change", onAwareness)

    return () => {
      nodesMap.unobserve(onNodesUpdate)
      edgesMap.unobserve(onEdgesUpdate)
      provider.awareness.off("change", onAwareness)
      provider.off("sync", onSync)
      provider.off("status", onStatus)
      provider.destroy()
      doc.destroy()
      bindingRef.current = null
      setConnected(false)
      setSynced(false)
      setUsers([])
      setCursors([])
    }
  }, [enabled, emitRemote, identity, room, token, url])

  const publish = useCallback((nodes: CanonicalWorkflowRecord[], edges: CanonicalWorkflowRecord[]) => {
    const binding = bindingRef.current
    if (!binding || !binding.initialized || applyingRemote.current) return
    binding.doc.transact(() => {
      const nextNodeIds = new Set(nodes.map((node) => node.id))
      for (const key of Array.from(binding.nodesMap.keys())) {
        if (!nextNodeIds.has(key)) binding.nodesMap.delete(key)
      }
      for (const node of nodes) setRecordIfChanged(binding.nodesMap, node)

      const nextEdgeIds = new Set(edges.map((edge) => edge.id))
      for (const key of Array.from(binding.edgesMap.keys())) {
        if (!nextEdgeIds.has(key)) binding.edgesMap.delete(key)
      }
      for (const edge of edges) setRecordIfChanged(binding.edgesMap, edge)
    }, LOCAL_ORIGIN)
  }, [])

  const initialize = useCallback((nodes: CanonicalWorkflowRecord[], edges: CanonicalWorkflowRecord[]) => {
    const binding = bindingRef.current
    if (!binding || !binding.provider.synced || binding.initialized) return
    binding.initialized = true
    if (binding.nodesMap.size || binding.edgesMap.size) {
      emitRemote()
      return
    }
    publish(nodes, edges)
  }, [emitRemote, publish])

  const publishCursor = useCallback((x: number, y: number) => {
    bindingRef.current?.provider.awareness.setLocalStateField("cursor", { x, y })
  }, [])

  const onRemote = useCallback((handler: (nodes: CanonicalWorkflowRecord[], edges: CanonicalWorkflowRecord[]) => void) => {
    remoteHandlerRef.current = handler
    const binding = bindingRef.current
    if (binding?.provider.synced && (binding.nodesMap.size || binding.edgesMap.size)) emitRemote()
    return () => {
      if (remoteHandlerRef.current === handler) remoteHandlerRef.current = null
    }
  }, [emitRemote])

  return useMemo(() => {
    if (!enabled) return NULL_BINDING
    return { authorized: Boolean(token), connected, synced, users, cursors, initialize, publish, publishCursor, onRemote }
  }, [connected, cursors, enabled, initialize, onRemote, publish, publishCursor, synced, token, users])
}
