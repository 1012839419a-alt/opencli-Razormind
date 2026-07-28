import type {
  ProjectRecordGraphPreview,
  RecordGraphEdge,
  RecordGraphNode,
} from '@/lib/api/types'
import {
  RECORD_GRAPH_KIND_COLOR,
  RECORD_GRAPH_KIND_LABEL,
} from '@/lib/records/project-record-graph'

export type ProjectForceNode = RecordGraphNode & {
  color: string
  degree: number
  displayLabel: string
  val: number
  x?: number
  y?: number
  z?: number
  fx?: number
  fy?: number
  fz?: number
  vx?: number
  vy?: number
  vz?: number
}

export type ProjectForceLink = Omit<RecordGraphEdge, 'source' | 'target'> & {
  source: string | ProjectForceNode
  target: string | ProjectForceNode
}

export type ProjectForceGraphData = {
  nodes: ProjectForceNode[]
  links: ProjectForceLink[]
}

export function forceNodeId(node: string | ProjectForceNode) {
  return typeof node === 'string' ? node : node.id
}

export function buildProjectForceGraph(
  preview: ProjectRecordGraphPreview,
): ProjectForceGraphData {
  const degree = new Map<string, number>()
  preview.edges.forEach((edge) => {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + edge.weight)
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + edge.weight)
  })

  return {
    nodes: preview.nodes.map((node) => {
      const nodeDegree = degree.get(node.id) ?? 0
      return {
        ...node,
        color: RECORD_GRAPH_KIND_COLOR[node.kind],
        degree: nodeDegree,
        displayLabel: node.label,
        val: Math.min(
          24,
          (node.kind === 'project' ? 8 : node.kind === 'record' ? 1.8 : 3.5)
            + Math.log1p(Math.max(node.count, nodeDegree)) * 1.7,
        ),
      }
    }),
    links: preview.edges.map((edge) => ({
      ...edge,
      source: edge.source,
      target: edge.target,
    })),
  }
}

type GalaxyPoint = { x: number; y: number; z: number }

type GalaxyNeighbor = {
  edge: ProjectForceLink
  nodeId: string
}

export function layoutStaticGalaxyNodes(
  nodes: ProjectForceNode[],
  links: ProjectForceLink[],
) {
  const nodesById = new Map(nodes.map((node) => [node.id, node]))
  const adjacency = new Map(nodes.map((node) => [node.id, [] as GalaxyNeighbor[]]))
  links.forEach((edge) => {
    const source = forceNodeId(edge.source)
    const target = forceNodeId(edge.target)
    if (!nodesById.has(source) || !nodesById.has(target)) return
    adjacency.get(source)?.push({ edge, nodeId: target })
    adjacency.get(target)?.push({ edge, nodeId: source })
  })

  const scale = Math.min(1.65, Math.max(0.9, Math.cbrt(nodes.length / 120)))
  const positions = new Map<string, GalaxyPoint>()
  const projects = nodes.filter((node) => node.kind === 'project').sort(compareNodeId)
  projects.forEach((node, index) => {
    positions.set(node.id, index === 0
      ? { x: 0, y: 0, z: 0 }
      : scalePoint(stableDirection(node.id), index * 18))
  })

  const records = nodes.filter((node) => node.kind === 'record').sort(compareNodeId)
  const sources = nodes.filter((node) => node.kind === 'source').sort(compareNodeId)
  const recordsBySource = new Map(sources.map((source) => [
    source.id,
    [] as ProjectForceNode[],
  ]))
  records.forEach((record) => {
    const source = findParent(record, ['source'], adjacency, nodesById)
    if (source) recordsBySource.get(source.id)?.push(record)
  })
  const largestSourceCluster = Math.max(
    64,
    ...sources.map((source) => sourceClusterRadius(
      recordsBySource.get(source.id)?.length ?? 0,
      scale,
    )),
  )
  const sourceOrbit = (175 + largestSourceCluster)
    * Math.max(1, Math.cbrt(Math.max(1, sources.length) / 2))
  sources.forEach((source, index) => {
    const center = siblingOffset(source.id, index, sources.length, sourceOrbit)
    positions.set(source.id, center)
    const members = recordsBySource.get(source.id) ?? []
    const radius = sourceClusterRadius(members.length, scale)
    members.forEach((record, recordIndex) => {
      positions.set(
        record.id,
        addPoint(center, clusterMemberOffset(
          record.id,
          recordIndex,
          members.length,
          radius,
        )),
      )
    })
  })

  const workflows = nodes.filter((node) => node.kind === 'workflow').sort(compareNodeId)
  workflows.forEach((node, index) => {
    const sourcePositions = (adjacency.get(node.id) ?? [])
      .map(({ nodeId }) => nodesById.get(nodeId))
      .filter((candidate): candidate is ProjectForceNode => candidate?.kind === 'source')
      .map((source) => positions.get(source.id))
      .filter((point): point is GalaxyPoint => Boolean(point))
    const center = sourcePositions.length
      ? scalePoint(averagePoints(sourcePositions), 0.48)
      : siblingOffset(node.id, index, workflows.length, 82 * scale)
    positions.set(node.id, center)
  })

  nodes
    .filter((node) => node.kind === 'run')
    .sort(compareNodeId)
    .forEach((node) => {
      const recordPositions = (adjacency.get(node.id) ?? [])
        .map(({ nodeId }) => nodesById.get(nodeId))
        .filter((candidate): candidate is ProjectForceNode => candidate?.kind === 'record')
        .map((record) => positions.get(record.id))
        .filter((point): point is GalaxyPoint => Boolean(point))
      const workflow = findParent(node, ['workflow'], adjacency, nodesById)
      const workflowPosition = workflow ? positions.get(workflow.id) : undefined
      const center = recordPositions.length
        ? averagePoints(recordPositions)
        : workflowPosition ?? { x: 0, y: 0, z: 0 }
      positions.set(node.id, addPoint(
        workflowPosition
          ? addPoint(scalePoint(workflowPosition, 0.35), scalePoint(center, 0.65))
          : center,
        scalePoint(stableDirection(node.id), 18 * scale),
      ))
    })

  placeChildren(
    records.filter((node) => !positions.has(node.id)),
    positions,
    adjacency,
    nodesById,
    ['run', 'workflow', 'project'],
    46 * scale,
  )

  nodes
    .filter((node) => node.kind === 'entity')
    .sort(compareNodeId)
    .forEach((node) => {
      const neighborPositions = (adjacency.get(node.id) ?? [])
        .map(({ nodeId }) => positions.get(nodeId))
        .filter((point): point is GalaxyPoint => Boolean(point))
      if (!neighborPositions.length) return
      const center = averagePoints(neighborPositions)
      const bridgeOffset = neighborPositions.length > 2 ? 10 : 24
      positions.set(node.id, addPoint(
        center,
        scalePoint(stableDirection(node.id), bridgeOffset * scale),
      ))
    })

  placeDetachedComponents(nodes, positions, adjacency, 340 * scale)
  placeOrphans(nodes, positions, adjacency, Math.max(430, sourceOrbit + largestSourceCluster + 90))

  nodes.forEach((node) => {
    const point = positions.get(node.id) ?? { x: 0, y: 0, z: 0 }
    node.x = node.fx = point.x
    node.y = node.fy = point.y
    node.z = node.fz = point.z
    node.vx = node.vy = node.vz = 0
  })
  return nodes
}

function sourceClusterRadius(memberCount: number, scale: number) {
  return (44 + Math.min(110, Math.sqrt(memberCount) * 9)) * scale
}

function clusterMemberOffset(
  id: string,
  index: number,
  total: number,
  radius: number,
) {
  const shell = 0.28 + 0.72 * Math.cbrt((index + 0.5) / Math.max(1, total))
  return siblingOffset(id, index, total, radius * shell)
}

function placeChildren(
  children: ProjectForceNode[],
  positions: Map<string, GalaxyPoint>,
  adjacency: Map<string, GalaxyNeighbor[]>,
  nodesById: Map<string, ProjectForceNode>,
  parentKinds: ProjectForceNode['kind'][],
  radius: number,
) {
  const grouped = new Map<string, ProjectForceNode[]>()
  children.sort(compareNodeId).forEach((node) => {
    const parent = findParent(node, parentKinds, adjacency, nodesById)
    if (!parent || !positions.has(parent.id)) return
    const siblings = grouped.get(parent.id) ?? []
    siblings.push(node)
    grouped.set(parent.id, siblings)
  })
  grouped.forEach((siblings, parentId) => {
    const center = positions.get(parentId)!
    const clusterRadius = radius * Math.min(
      1.8,
      Math.max(1, Math.cbrt(siblings.length / 12)),
    )
    siblings.forEach((node, index) => {
      positions.set(node.id, addPoint(
        center,
        siblingOffset(node.id, index, siblings.length, clusterRadius),
      ))
    })
  })
}

function findParent(
  node: ProjectForceNode,
  preferredKinds: ProjectForceNode['kind'][],
  adjacency: Map<string, GalaxyNeighbor[]>,
  nodesById: Map<string, ProjectForceNode>,
) {
  const neighbors = (adjacency.get(node.id) ?? [])
    .map(({ edge, nodeId }) => ({ edge, node: nodesById.get(nodeId) }))
    .filter((item): item is { edge: ProjectForceLink; node: ProjectForceNode } => (
      Boolean(item.node)
    ))

  for (const kind of preferredKinds) {
    const matching = neighbors
      .filter(({ node: candidate }) => candidate.kind === kind)
      .sort((left, right) => (
        relationPriority(right.edge.kind) - relationPriority(left.edge.kind)
        || right.edge.weight - left.edge.weight
        || compareNodeId(left.node, right.node)
      ))
    if (matching[0]) return matching[0].node
  }

  const metadataIds = [
    node.source_id ? `source:${node.source_id}` : '',
    node.workflow_run_id ? `run:${node.workflow_run_id}` : '',
    node.workflow_id ? `workflow:${node.workflow_id}` : '',
  ]
  return metadataIds
    .map((id) => nodesById.get(id))
    .find((candidate) => candidate && preferredKinds.includes(candidate.kind))
}

function placeDetachedComponents(
  nodes: ProjectForceNode[],
  positions: Map<string, GalaxyPoint>,
  adjacency: Map<string, GalaxyNeighbor[]>,
  radius: number,
) {
  const remaining = new Set(
    nodes
      .filter((node) => !positions.has(node.id) && (adjacency.get(node.id)?.length ?? 0) > 0)
      .map((node) => node.id),
  )
  let componentIndex = 0
  while (remaining.size) {
    const first = [...remaining].sort()[0]!
    const component: string[] = []
    const queue = [first]
    remaining.delete(first)
    while (queue.length) {
      const current = queue.shift()!
      component.push(current)
      for (const { nodeId } of adjacency.get(current) ?? []) {
        if (!remaining.delete(nodeId)) continue
        queue.push(nodeId)
      }
    }
    component.sort()
    const center = scalePoint(
      stableDirection(`component:${component[0]}`),
      radius + componentIndex * 35,
    )
    const hub = [...component].sort((left, right) => (
      (adjacency.get(right)?.length ?? 0) - (adjacency.get(left)?.length ?? 0)
      || left.localeCompare(right)
    ))[0]!
    positions.set(hub, center)
    const pending = component.filter((id) => id !== hub)
    for (let pass = 0; pending.length && pass < component.length; pass += 1) {
      for (let index = pending.length - 1; index >= 0; index -= 1) {
        const id = pending[index]!
        const placedNeighbors = (adjacency.get(id) ?? [])
          .map(({ nodeId }) => positions.get(nodeId))
          .filter((point): point is GalaxyPoint => Boolean(point))
        if (!placedNeighbors.length) continue
        positions.set(id, addPoint(
          averagePoints(placedNeighbors),
          scalePoint(stableDirection(id), 58),
        ))
        pending.splice(index, 1)
      }
    }
    pending.forEach((id, index) => {
      positions.set(id, addPoint(center, siblingOffset(id, index, pending.length, 72)))
    })
    componentIndex += 1
  }
}

function placeOrphans(
  nodes: ProjectForceNode[],
  positions: Map<string, GalaxyPoint>,
  adjacency: Map<string, GalaxyNeighbor[]>,
  radius: number,
) {
  const orphans = nodes
    .filter((node) => (
      node.kind !== 'project'
      && (adjacency.get(node.id)?.length ?? 0) === 0
    ))
    .sort(compareNodeId)
  orphans.forEach((node, index) => {
    positions.set(
      node.id,
      siblingOffset(node.id, index, orphans.length, radius + (index % 3) * 28),
    )
  })
}

function relationPriority(kind: ProjectForceLink['kind']) {
  if (kind === 'origin') return 7
  if (kind === 'produced') return 6
  if (kind === 'contains') return 5
  if (kind === 'semantic') return 4
  if (kind === 'reference') return 3
  if (kind === 'batch') return 2
  return 1
}

function compareNodeId(left: ProjectForceNode, right: ProjectForceNode) {
  return left.id.localeCompare(right.id)
}

function siblingOffset(
  id: string,
  index: number,
  total: number,
  radius: number,
) {
  if (total <= 1) return scalePoint(stableDirection(id), radius)
  const y = 1 - (2 * (index + 0.5)) / total
  const planar = Math.sqrt(Math.max(0, 1 - y * y))
  const angle = index * 2.399963229728653
    + hashUnit(projectForceNodeHash(id), 0x9e3779b9) * Math.PI * 2
  return {
    x: Math.cos(angle) * planar * radius,
    y: y * radius,
    z: Math.sin(angle) * planar * radius,
  }
}

function stableDirection(id: string) {
  const hash = projectForceNodeHash(id)
  const y = hashUnit(hash, 0x85ebca6b) * 2 - 1
  const angle = hashUnit(hash, 0xc2b2ae35) * Math.PI * 2
  const planar = Math.sqrt(Math.max(0, 1 - y * y))
  return { x: Math.cos(angle) * planar, y, z: Math.sin(angle) * planar }
}

function averagePoints(points: GalaxyPoint[]) {
  const sum = points.reduce(addPoint, { x: 0, y: 0, z: 0 })
  return scalePoint(sum, 1 / points.length)
}

function addPoint(left: GalaxyPoint, right: GalaxyPoint) {
  return { x: left.x + right.x, y: left.y + right.y, z: left.z + right.z }
}

function scalePoint(point: GalaxyPoint, scale: number) {
  return { x: point.x * scale, y: point.y * scale, z: point.z * scale }
}

export function projectForceNodeHash(value: string) {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function hashUnit(hash: number, salt: number) {
  let value = hash ^ salt
  value = Math.imul(value ^ (value >>> 16), 0x7feb352d)
  value = Math.imul(value ^ (value >>> 15), 0x846ca68b)
  return ((value ^ (value >>> 16)) >>> 0) / 4294967296
}

export function projectForceNodeTooltip(node: ProjectForceNode) {
  const subtitle = node.subtitle ?? node.preview
  return [
    `<strong>${escapeHtml(node.displayLabel)}</strong>`,
    `<span>${RECORD_GRAPH_KIND_LABEL[node.kind]} · ${node.degree} 条关系</span>`,
    subtitle ? `<small>${escapeHtml(subtitle.slice(0, 140))}</small>` : '',
  ].filter(Boolean).join('<br />')
}

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}
