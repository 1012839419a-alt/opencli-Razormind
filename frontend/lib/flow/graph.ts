// Graph helpers used by "Prevent Cycles", "Connection Limit" and "Validation".
// All functions are pure so they can be unit-tested and reused server-side.

import type { Edge, Node, Connection } from "@xyflow/react"

export type HandleDirection = "source" | "target"
type NodePort = { id?: string; name?: string; direction?: string; type?: string }

export type NodeHandleDescriptor = {
  id: string | null
  name: string
  type: string
  direction: HandleDirection
}

/** Would adding `source → target` introduce a directed cycle in `edges`? */
export function wouldCreateCycle(edges: Edge[], source: string, target: string): boolean {
  if (source === target) return true
  // BFS from target — if we can reach source, adding source→target closes a cycle.
  const adj = new Map<string, string[]>()
  for (const e of edges) {
    if (!e.source || !e.target) continue
    const arr = adj.get(e.source) ?? []
    arr.push(e.target)
    adj.set(e.source, arr)
  }
  const stack = [target]
  const seen = new Set<string>()
  while (stack.length > 0) {
    const cur = stack.pop()!
    if (cur === source) return true
    if (seen.has(cur)) continue
    seen.add(cur)
    const next = adj.get(cur)
    if (next) stack.push(...next)
  }
  return false
}

/** Count how many edges already touch a given (node, handle, direction). */
export function countHandleConnections(
  edges: Edge[],
  nodeId: string,
  handleId: string | null | undefined,
  direction: "source" | "target",
): number {
  return edges.filter((e) => {
    if (direction === "source") {
      if (e.source !== nodeId) return false
      return (e.sourceHandle ?? null) === (handleId ?? null)
    } else {
      if (e.target !== nodeId) return false
      return (e.targetHandle ?? null) === (handleId ?? null)
    }
  }).length
}

export interface ValidateConnectionOptions {
  /** false → allow cycles */
  preventCycles: boolean
  /** max outgoing edges per source handle. undefined = unlimited */
  maxSourceConnections?: number
  /** max incoming edges per target handle. undefined = unlimited */
  maxTargetConnections?: number
  /** if a node type carries `handleType`, target must match source */
  typedHandles?: boolean
  nodes?: Node[]
}

function nodePorts(node: Node, direction: HandleDirection): NodePort[] {
  const data = node.data as Record<string, unknown>
  const primitivePorts = Array.isArray(data.primitivePorts) ? data.primitivePorts as NodePort[] : []
  if (primitivePorts.length > 0) {
    const expected = direction === "source" ? "output" : "input"
    return primitivePorts.filter((port) => port.direction === expected)
  }

  const contract = data.runtimeContract as {
    inputShape?: { ports?: NodePort[] }
    outputShape?: { ports?: NodePort[] }
  } | undefined
  return direction === "source"
    ? contract?.outputShape?.ports ?? []
    : contract?.inputShape?.ports ?? []
}

export function nodeHandleDescriptors(node: Node, direction: HandleDirection): NodeHandleDescriptor[] {
  if (node.type && node.type !== "workflow") return []
  const descriptors = nodePorts(node, direction).map((port) => ({
    id: port.id ?? port.name ?? null,
    name: port.name ?? port.id ?? (direction === "source" ? "output" : "input"),
    type: port.type ?? "unknown",
    direction,
  }))
  return descriptors.length > 0
    ? descriptors
    : [{ id: null, name: direction === "source" ? "output" : "input", type: "unknown", direction }]
}

export function nodeHandleIds(node: Node, direction: HandleDirection): Array<string | null> {
  return nodeHandleDescriptors(node, direction).map((port) => port.id)
}

export function nodeHandleDescriptor(
  node: Node | undefined,
  handleId: string | null | undefined,
  direction: HandleDirection,
): NodeHandleDescriptor | undefined {
  return node
    ? nodeHandleDescriptors(node, direction).find((port) => port.id === (handleId ?? null))
    : undefined
}

export function portTypesCompatible(sourceType: string, targetType: string): boolean {
  const source = sourceType.trim().toLowerCase()
  const target = targetType.trim().toLowerCase()
  return source === target || source === "any" || target === "any" || source === "unknown" || target === "unknown"
}

function nodeHandleType(node: Node | undefined, handleId: string | null | undefined, direction: HandleDirection) {
  return nodeHandleDescriptor(node, handleId, direction)?.type
}

export function insertionConnections(
  nodes: Node[],
  edges: Edge[],
  edge: Edge,
  node: Node,
): [Connection, Connection] | null {
  if (node.id === edge.source || node.id === edge.target) return null
  const withoutEdge = edges.filter((candidate) => candidate.id !== edge.id)
  for (const input of nodeHandleDescriptors(node, "target")) {
    const incoming: Connection = {
      source: edge.source,
      sourceHandle: edge.sourceHandle ?? null,
      target: node.id,
      targetHandle: input.id,
    }
    if (!validateConnection(withoutEdge, incoming, { preventCycles: true, typedHandles: true, nodes }).ok) continue
    for (const output of nodeHandleDescriptors(node, "source")) {
      const outgoing: Connection = {
        source: node.id,
        sourceHandle: output.id,
        target: edge.target,
        targetHandle: edge.targetHandle ?? null,
      }
      if (validateConnection([...withoutEdge, incoming as Edge], outgoing, {
        preventCycles: true,
        typedHandles: true,
        nodes,
      }).ok) {
        return [incoming, outgoing]
      }
    }
  }
  return null
}

export function validateConnection(
  edges: Edge[],
  connection: Connection,
  opts: ValidateConnectionOptions,
): { ok: true } | { ok: false; reason: string } {
  const { source, target, sourceHandle, targetHandle } = connection
  if (!source || !target) return { ok: false, reason: "缺少端点" }
  if (source === target) return { ok: false, reason: "不能自连" }

  if (opts.preventCycles && wouldCreateCycle(edges, source, target)) {
    return { ok: false, reason: "该连线会形成环" }
  }

  if (typeof opts.maxSourceConnections === "number") {
    if (countHandleConnections(edges, source, sourceHandle, "source") >= opts.maxSourceConnections) {
      return { ok: false, reason: `输出端口最多 ${opts.maxSourceConnections} 条连线` }
    }
  }
  if (typeof opts.maxTargetConnections === "number") {
    if (countHandleConnections(edges, target, targetHandle, "target") >= opts.maxTargetConnections) {
      return { ok: false, reason: `输入端口最多 ${opts.maxTargetConnections} 条连线` }
    }
  }

  if (opts.typedHandles && opts.nodes) {
    const s = opts.nodes.find((n) => n.id === source)
    const t = opts.nodes.find((n) => n.id === target)
    const sType = nodeHandleType(s, sourceHandle, "source")
      ?? (s?.data as { handleType?: string } | undefined)?.handleType
    const tType = nodeHandleType(t, targetHandle, "target")
      ?? (t?.data as { handleType?: string } | undefined)?.handleType
    if (sType && tType && !portTypesCompatible(sType, tType)) {
      return { ok: false, reason: `端口类型不兼容：${sType} → ${tType}` }
    }
  }

  return { ok: true }
}
