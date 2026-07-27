import type { WorkflowEdge, WorkflowNode } from "@/lib/flow/types"

export type WorkflowOutlineRow = {
  nodeId: string
  depth: number
  branchLabel?: string
  disconnected: boolean
}

function compareNodes(left: WorkflowNode, right: WorkflowNode) {
  return left.position.y - right.position.y
    || left.position.x - right.position.x
    || left.id.localeCompare(right.id)
}

function edgeBranchLabel(edge: WorkflowEdge) {
  const label = edge.data?.label
  if (typeof label === "string" && label.trim()) return label.trim()
  return edge.sourceHandle?.trim() || undefined
}

export function buildWorkflowOutlineRows(
  nodes: WorkflowNode[],
  edges: WorkflowEdge[],
): WorkflowOutlineRow[] {
  const visibleNodes = nodes.filter((node) => !node.hidden).sort(compareNodes)
  const nodeById = new Map(visibleNodes.map((node) => [node.id, node]))
  const incoming = new Map(visibleNodes.map((node) => [node.id, 0]))
  const outgoing = new Map<string, WorkflowEdge[]>()

  for (const edge of edges) {
    if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) continue
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1)
    outgoing.set(edge.source, [...(outgoing.get(edge.source) ?? []), edge])
  }

  const rows: WorkflowOutlineRow[] = []
  const visited = new Set<string>()
  const visit = (
    nodeId: string,
    depth: number,
    branchLabel: string | undefined,
    disconnected: boolean,
  ) => {
    if (visited.has(nodeId)) return
    visited.add(nodeId)
    rows.push({ nodeId, depth, branchLabel, disconnected })
    const nextEdges = [...(outgoing.get(nodeId) ?? [])].sort((left, right) => {
      const leftNode = nodeById.get(left.target)
      const rightNode = nodeById.get(right.target)
      return leftNode && rightNode ? compareNodes(leftNode, rightNode) : left.target.localeCompare(right.target)
    })
    for (const edge of nextEdges) {
      visit(edge.target, depth + 1, edgeBranchLabel(edge), disconnected)
    }
  }

  const roots = visibleNodes.filter((node) => (incoming.get(node.id) ?? 0) === 0 && (outgoing.get(node.id)?.length ?? 0) > 0)
  for (const root of roots) visit(root.id, 0, undefined, false)
  for (const node of visibleNodes) {
    if (!visited.has(node.id)) visit(node.id, 0, undefined, true)
  }
  return rows
}
