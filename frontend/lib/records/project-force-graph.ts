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

export type ProjectForceLink = RecordGraphEdge & {
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
