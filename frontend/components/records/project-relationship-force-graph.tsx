'use client'

import { Settings2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, {
  type ForceGraphMethods,
} from 'react-force-graph-2d'

import {
  DEFAULT_PROJECT_RELATIONSHIP_SETTINGS,
  ProjectRelationshipControlPanel,
  type ProjectRelationshipSettings,
} from '@/components/records/project-relationship-control-panel'
import type { ProjectRecordGraphPreview } from '@/lib/api/types'
import {
  buildProjectForceGraph,
  forceNodeId,
  projectForceNodeTooltip,
  type ProjectForceLink,
  type ProjectForceNode,
} from '@/lib/records/project-force-graph'

type ProjectRelationshipForceGraphProps = {
  preview: ProjectRecordGraphPreview
  selectedNodeId: string | null
  onSelectNode: (nodeId: string | null) => void
}

export function ProjectRelationshipForceGraph({
  preview,
  selectedNodeId,
  onSelectNode,
}: ProjectRelationshipForceGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<ForceGraphMethods<ProjectForceNode, ProjectForceLink> | undefined>(undefined)
  const [size, setSize] = useState({ width: 800, height: 720 })
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [panelOpen, setPanelOpen] = useState(false)
  const [settings, setSettings] = useState<ProjectRelationshipSettings>({
    ...DEFAULT_PROJECT_RELATIONSHIP_SETTINGS,
  })
  const storageKey = useMemo(() => {
    const projectNode = preview.nodes.find((node) => node.kind === 'project')
    return `opencli:project-relationships:${projectNode?.id ?? 'default'}`
  }, [preview.nodes])
  const graphData = useMemo(() => {
    const data = buildProjectForceGraph(preview)
    if (settings.showOrphans) return data
    const connected = new Set(data.links.flatMap((link) => [
      forceNodeId(link.source),
      forceNodeId(link.target),
    ]))
    return {
      nodes: data.nodes.filter((node) => connected.has(node.id)),
      links: data.links,
    }
  }, [preview, settings.showOrphans])
  const neighbors = useMemo(
    () => connectedNodeIds(graphData.links, selectedNodeId ?? hoveredNodeId),
    [graphData.links, hoveredNodeId, selectedNodeId],
  )

  useEffect(() => {
    const saved = window.localStorage.getItem(storageKey)
    if (!saved) return
    try {
      const parsed = JSON.parse(saved) as Partial<ProjectRelationshipSettings>
      setSettings({ ...DEFAULT_PROJECT_RELATIONSHIP_SETTINGS, ...parsed })
    } catch {
      setSettings({ ...DEFAULT_PROJECT_RELATIONSHIP_SETTINGS })
    }
  }, [storageKey])

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(settings))
  }, [settings, storageKey])

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.max(320, Math.floor(entry.contentRect.width))
      const height = Math.max(560, Math.floor(entry.contentRect.height))
      setSize({ width, height })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const graph = graphRef.current
    if (!graph) return
    const charge = graph.d3Force('charge')
    if (charge && 'strength' in charge && typeof charge.strength === 'function') {
      charge.strength(-settings.repelStrength)
    }
    const link = graph.d3Force('link')
    if (link && 'distance' in link && typeof link.distance === 'function') {
      link.distance(settings.linkDistance)
    }
    if (link && 'strength' in link && typeof link.strength === 'function') {
      link.strength(settings.linkStrength)
    }
    const center = graph.d3Force('center')
    if (center && 'strength' in center && typeof center.strength === 'function') {
      center.strength(settings.centerStrength)
    }
    graph.d3ReheatSimulation()
    const fitTimer = window.setTimeout(() => graph.zoomToFit(600, 56), 450)
    return () => window.clearTimeout(fitTimer)
  }, [
    graphData,
    settings.centerStrength,
    settings.linkDistance,
    settings.linkStrength,
    settings.repelStrength,
  ])

  const focusNode = useCallback((node: ProjectForceNode) => {
    onSelectNode(node.id)
    if (typeof node.x !== 'number' || typeof node.y !== 'number') return
    graphRef.current?.centerAt(node.x, node.y, 420)
    graphRef.current?.zoom(1.8, 420)
  }, [onSelectNode])

  const drawNode = useCallback((
    node: ProjectForceNode,
    context: CanvasRenderingContext2D,
    globalScale: number,
  ) => {
    if (typeof node.x !== 'number' || typeof node.y !== 'number') return
    const activeId = selectedNodeId ?? hoveredNodeId
    const isSelected = node.id === selectedNodeId
    const isNeighbor = neighbors.has(node.id)
    const muted = settings.fadeUnrelated && Boolean(activeId) && !isSelected && !isNeighbor
    const radius = Math.max(
      1.7,
      Math.min(5.8, Math.sqrt(node.val) * 1.05),
    ) * settings.nodeSize

    context.save()
    context.globalAlpha = muted ? 0.09 : isSelected ? 1 : 0.82
    context.shadowColor = isSelected ? '#ffffff' : 'transparent'
    context.shadowBlur = isSelected ? 10 / globalScale : 0
    context.beginPath()
    context.arc(node.x, node.y, radius, 0, Math.PI * 2)
    context.fillStyle = node.color
    context.fill()
    if (isSelected) {
      context.lineWidth = 1.1 / globalScale
      context.strokeStyle = '#dcddde'
      context.stroke()
    }

    const shouldLabel = settings.showLabels && (isSelected
      || node.id === hoveredNodeId
      || node.kind === 'project'
      || (globalScale > 1.7 && node.kind !== 'record')
      || (globalScale > 2.7 && node.degree > 2))
    if (shouldLabel) {
      const fontSize = Math.max(9.5 / globalScale, 3)
      context.font = `${isSelected ? 600 : 400} ${fontSize}px Inter, system-ui, sans-serif`
      context.textAlign = 'left'
      context.textBaseline = 'middle'
      context.fillStyle = muted ? '#66676a' : '#c7c8ca'
      context.fillText(
        compactLabel(node.displayLabel, isSelected ? 48 : 30),
        node.x + radius + 3 / globalScale,
        node.y,
      )
    }
    context.restore()
  }, [
    hoveredNodeId,
    neighbors,
    selectedNodeId,
    settings.fadeUnrelated,
    settings.nodeSize,
    settings.showLabels,
  ])

  return (
    <div ref={containerRef} className="relative h-full min-h-[44rem] w-full overflow-hidden bg-[#1e1e1e]">
      <button
        type="button"
        onClick={() => setPanelOpen((open) => !open)}
        className="absolute left-3 top-3 z-20 flex min-h-9 items-center gap-2 rounded-md border border-white/10 bg-[#242424]/90 px-3 text-xs text-zinc-300 shadow-lg backdrop-blur hover:bg-[#303030]"
        aria-pressed={panelOpen}
      >
        <Settings2 className="size-3.5" />
        图谱控制
      </button>
      {panelOpen ? (
        <ProjectRelationshipControlPanel
          settings={settings}
          onChange={setSettings}
          onClose={() => setPanelOpen(false)}
          onRecenter={() => graphRef.current?.zoomToFit(600, 56)}
        />
      ) : null}
      <ForceGraph2D<ProjectForceNode, ProjectForceLink>
        ref={graphRef}
        width={size.width}
        height={size.height}
        graphData={graphData}
        backgroundColor="#1e1e1e"
        nodeId="id"
        nodeVal="val"
        nodeLabel={projectForceNodeTooltip}
        nodeCanvasObject={drawNode}
        nodePointerAreaPaint={(node, color, context) => {
          if (typeof node.x !== 'number' || typeof node.y !== 'number') return
          context.beginPath()
          context.arc(node.x, node.y, Math.max(5, Math.sqrt(node.val) * 2), 0, Math.PI * 2)
          context.fillStyle = color
          context.fill()
        }}
        linkColor={(link) => relationshipColor(link, selectedNodeId ?? hoveredNodeId)}
        linkWidth={(link) => {
          const activeId = selectedNodeId ?? hoveredNodeId
          const base = !activeId
            ? Math.min(1.3, 0.18 + Math.log1p(link.weight) * 0.2)
            : touches(link, activeId) ? 1.45 : 0.18
          return base * settings.linkThickness
        }}
        linkCurvature={0}
        linkDirectionalArrowLength={0}
        cooldownTicks={220}
        d3VelocityDecay={0.32}
        enableNodeDrag
        minZoom={0.25}
        maxZoom={8}
        onNodeHover={(node) => setHoveredNodeId(node?.id ?? null)}
        onNodeClick={(node) => focusNode(node)}
        onBackgroundClick={() => onSelectNode(null)}
      />
    </div>
  )
}

function connectedNodeIds(links: ProjectForceLink[], nodeId: string | null) {
  const ids = new Set<string>()
  if (!nodeId) return ids
  ids.add(nodeId)
  links.forEach((link) => {
    const source = forceNodeId(link.source)
    const target = forceNodeId(link.target)
    if (source === nodeId) ids.add(target)
    if (target === nodeId) ids.add(source)
  })
  return ids
}

function touches(link: ProjectForceLink, nodeId: string) {
  return forceNodeId(link.source) === nodeId || forceNodeId(link.target) === nodeId
}

function relationshipColor(link: ProjectForceLink, activeNodeId: string | null) {
  if (!activeNodeId) return 'rgba(136, 136, 136, 0.28)'
  return touches(link, activeNodeId)
    ? 'rgba(190, 190, 190, 0.72)'
    : 'rgba(90, 90, 90, 0.06)'
}

function compactLabel(label: string, limit: number) {
  return label.length > limit ? `${label.slice(0, limit - 1)}…` : label
}
