"use client"

import { useEffect, useRef } from "react"
import { useReactFlow, useStore } from "@xyflow/react"
import { useFlowStore } from "@/lib/flow/store"
import { useSettingsStore } from "@/lib/flow/settings-store"
import { useYjs } from "@/lib/flow/yjs-provider"
import { persistableWorkflowProject } from "@/lib/workflow/persistence"

export function Collaboration() {
  const provider = useSettingsStore((state) => state.collabProvider)
  const yjsUrl = useSettingsStore((state) => state.yjsUrl)
  const yjsRoom = useSettingsStore((state) => state.yjsRoom)
  const yjsEnabled = useSettingsStore((state) => state.yjsEnabled)
  const configured = yjsEnabled && provider === "yjs"
  const enabled = configured && Boolean(yjsUrl) && Boolean(yjsRoom)
  const binding = useYjs(enabled, { url: yjsUrl, room: yjsRoom })
  const transportEnabled = enabled && binding.authorized
  const { screenToFlowPosition } = useReactFlow()
  const transform = useStore((state) => state.transform)
  const applyingRemote = useRef(false)

  useEffect(() => {
    const ready = binding.connected && binding.synced
    const settings = useSettingsStore.getState()
    if (settings.yjsConnected !== ready) settings.patch({ yjsConnected: ready })
  }, [binding.connected, binding.synced])

  // Incoming updates are canonical WorkflowProject records. Projecting them
  // here keeps the canvas and the full-PUT fallback on the same source graph.
  useEffect(() => {
    if (!transportEnabled) return
    return binding.onRemote((nodes, edges) => {
      applyingRemote.current = true
      const current = useFlowStore.getState()
      const { drawings, workflowProject } = current
      current.importWorkflowProject({
        ...workflowProject,
        nodes: nodes as typeof workflowProject.nodes,
        edges: edges as typeof workflowProject.edges,
      })
      useFlowStore.setState({ drawings })
      queueMicrotask(() => {
        applyingRemote.current = false
      })
    })
  }, [binding, transportEnabled])

  // A synced, non-empty room is authoritative. Only seed once for a room that
  // contains no graph yet, then publish subsequent local canonical changes.
  useEffect(() => {
    if (!transportEnabled) return
    const unsubscribe = useFlowStore.subscribe((state, previous) => {
      if (applyingRemote.current || state.workflowProject === previous.workflowProject) return
      const persistable = persistableWorkflowProject(state.workflowProject)
      binding.publish(persistable.nodes, persistable.edges)
    })
    const persistable = persistableWorkflowProject(useFlowStore.getState().workflowProject)
    binding.initialize(persistable.nodes, persistable.edges)
    return unsubscribe
  }, [binding, transportEnabled])

  useEffect(() => {
    if (!transportEnabled) return
    let raf = 0
    const onMove = (event: MouseEvent) => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
        binding.publishCursor(position.x, position.y)
      })
    }
    window.addEventListener("mousemove", onMove)
    return () => {
      window.removeEventListener("mousemove", onMove)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [binding, screenToFlowPosition, transportEnabled])

  if (!configured) return null
  const [tx, ty, zoom] = transform
  const stateLabel = !binding.authorized ? "○ TOKEN REQUIRED" : binding.connected ? binding.synced ? "● LIVE" : "○ SYNCING" : "○ OFFLINE"
  const stateClassName = binding.connected && binding.synced ? "text-[#4ade80]" : "text-[#ff7a17]"

  return (
    <>
      <div className="pointer-events-none absolute inset-0 z-20 overflow-hidden">
        {binding.cursors.map((cursor) => (
          <div
            key={cursor.id}
            className="absolute flex items-center gap-1"
            style={{ transform: `translate(${tx + cursor.x * zoom}px, ${ty + cursor.y * zoom}px)` }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" style={{ color: cursor.color }}>
              <path fill="currentColor" d="M4 2l6 16 2.5-6.5L19 9z" />
            </svg>
            <span
              className="rounded px-1.5 py-0.5 text-[10px] font-medium text-white shadow"
              style={{ backgroundColor: cursor.color }}
            >
              {cursor.name}
            </span>
          </div>
        ))}
      </div>

      <div className="pointer-events-none absolute right-3 top-3 z-30 flex items-center gap-2 rounded-md border bg-card/90 px-2 py-1 font-mono text-[10px] shadow backdrop-blur">
        <span className={stateClassName}>{stateLabel}</span>
        <span className="text-muted-foreground">·</span>
        <span className="text-muted-foreground">room {yjsRoom}</span>
        {binding.users.length > 0 ? (
          <>
            <span className="text-muted-foreground">·</span>
            <div className="flex -space-x-1">
              {binding.users.slice(0, 6).map((user) => (
                <span
                  key={user.id}
                  className="flex size-4 items-center justify-center rounded-full border border-background text-[8px] font-semibold text-white"
                  style={{ backgroundColor: user.color }}
                  title={user.name}
                >
                  {user.name[0]?.toUpperCase()}
                </span>
              ))}
            </div>
          </>
        ) : null}
      </div>
    </>
  )
}
