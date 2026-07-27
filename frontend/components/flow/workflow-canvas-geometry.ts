import type { MouseEvent as ReactMouseEvent } from "react"

export type CanvasPoint = { x: number; y: number }

function distance(a: CanvasPoint, b: CanvasPoint) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

export function edgeIdsAtScreenPoint(point: CanvasPoint, threshold = 10): string[] {
  const hits: string[] = []
  const edges = document.querySelectorAll<SVGGElement>(".react-flow__edge[data-id]")

  edges.forEach((edge) => {
    const id = edge.dataset.id
    const path = edge.querySelector<SVGPathElement>("path.react-flow__edge-path, path[id]")
    if (!id || !path) return
    const ctm = path.getScreenCTM()
    if (!ctm) return

    const total = path.getTotalLength()
    const steps = Math.max(16, Math.ceil(total / 18))
    for (let i = 0; i <= steps; i++) {
      const svgPoint = path.getPointAtLength((total * i) / steps)
      const screenPoint = new DOMPoint(svgPoint.x, svgPoint.y).matrixTransform(ctm)
      if (distance(point, screenPoint) <= threshold) {
        hits.push(id)
        return
      }
    }
  })

  return hits
}

export function edgeIdIntersectingNode(
  nodeId: string,
  excludedEdgeIds: ReadonlySet<string>,
  threshold = 12,
): string | null {
  const node = [...document.querySelectorAll<HTMLElement>(".react-flow__node[data-id]")]
    .find((candidate) => candidate.dataset.id === nodeId)
  if (!node) return null
  const rect = node.getBoundingClientRect()
  const expanded = {
    left: rect.left - threshold,
    right: rect.right + threshold,
    top: rect.top - threshold,
    bottom: rect.bottom + threshold,
  }

  for (const edge of document.querySelectorAll<SVGGElement>(".react-flow__edge[data-id]")) {
    const id = edge.dataset.id
    const path = edge.querySelector<SVGPathElement>("path.react-flow__edge-path, path[id]")
    if (!id || excludedEdgeIds.has(id) || !path) continue
    const ctm = path.getScreenCTM()
    if (!ctm) continue
    const total = path.getTotalLength()
    const steps = Math.max(16, Math.ceil(total / 18))
    for (let index = 0; index <= steps; index++) {
      const point = path.getPointAtLength((total * index) / steps)
      const screen = new DOMPoint(point.x, point.y).matrixTransform(ctm)
      if (
        screen.x >= expanded.left &&
        screen.x <= expanded.right &&
        screen.y >= expanded.top &&
        screen.y <= expanded.bottom
      ) {
        return id
      }
    }
  }
  return null
}

export function localPoint(element: HTMLElement | null, event: ReactMouseEvent): CanvasPoint {
  const rect = element?.getBoundingClientRect()
  if (!rect) return { x: event.clientX, y: event.clientY }
  return { x: event.clientX - rect.left, y: event.clientY - rect.top }
}
