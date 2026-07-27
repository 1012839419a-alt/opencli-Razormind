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
    const nextEdges = [...(outgoing.get(nodeId) ?? [])].sort((left, right) => {
      const leftNode = nodeById.get(left.target)
      const rightNode = nodeById.get(right.target)
      return leftNode && rightNode ? compareNodes(leftNode, rightNode) : left.target.localeCompare(right.target)
    })
    rows.push({ nodeId, depth, branchLabel, disconnected })
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

export function visibleWorkflowOutlineRows(
  rows: WorkflowOutlineRow[],
  collapsedNodeIds: ReadonlySet<string>,
): WorkflowOutlineRow[] {
  const visible: WorkflowOutlineRow[] = []
  let hiddenBelowDepth: number | undefined

  for (const [index, row] of rows.entries()) {
    if (hiddenBelowDepth !== undefined && row.depth > hiddenBelowDepth) continue
    hiddenBelowDepth = undefined
    visible.push(row)
    if (workflowOutlineRowHasChildren(rows, index) && collapsedNodeIds.has(row.nodeId)) {
      hiddenBelowDepth = row.depth
    }
  }

  return visible
}

export function filterWorkflowOutlineRows(
  rows: WorkflowOutlineRow[],
  query: string,
  searchTextForNode: (nodeId: string) => string,
): WorkflowOutlineRow[] {
  const normalizedQuery = query.trim().toLocaleLowerCase()
  if (!normalizedQuery) return rows

  const includedIndexes = new Set<number>()
  for (const [index, row] of rows.entries()) {
    if (!searchTextForNode(row.nodeId).toLocaleLowerCase().includes(normalizedQuery)) continue
    includedIndexes.add(index)
    let expectedParentDepth = row.depth - 1
    for (let ancestorIndex = index - 1; ancestorIndex >= 0 && expectedParentDepth >= 0; ancestorIndex -= 1) {
      if (rows[ancestorIndex].depth !== expectedParentDepth) continue
      includedIndexes.add(ancestorIndex)
      expectedParentDepth -= 1
    }
  }
  return rows.filter((_, index) => includedIndexes.has(index))
}

export function workflowOutlineRowHasChildren(
  rows: WorkflowOutlineRow[],
  rowIndex: number,
): boolean {
  const row = rows[rowIndex]
  const next = rows[rowIndex + 1]
  return Boolean(row && next && next.depth > row.depth)
}

export function workflowUpstreamNodeIds(
  nodeId: string,
  edges: WorkflowEdge[],
): Set<string> {
  const sourcesByTarget = new Map<string, string[]>()
  for (const edge of edges) {
    sourcesByTarget.set(edge.target, [...(sourcesByTarget.get(edge.target) ?? []), edge.source])
  }

  const upstream = new Set<string>()
  const queue = [...(sourcesByTarget.get(nodeId) ?? [])]
  while (queue.length > 0) {
    const source = queue.shift()
    if (!source || upstream.has(source) || source === nodeId) continue
    upstream.add(source)
    queue.push(...(sourcesByTarget.get(source) ?? []))
  }
  return upstream
}

export function workflowDirectUpstreamNodeIds(
  nodeId: string,
  edges: WorkflowEdge[],
): Set<string> {
  return new Set(
    edges
      .filter((edge) => edge.target === nodeId)
      .map((edge) => edge.source),
  )
}

const WORKFLOW_INPUT_REFERENCE_PATH = /^[A-Za-z_][\w.-]*$/

export function workflowInputReferenceForPort(portId: string): string | undefined {
  const path = portId.trim()
  return WORKFLOW_INPUT_REFERENCE_PATH.test(path) ? `{{${path}}}` : undefined
}
