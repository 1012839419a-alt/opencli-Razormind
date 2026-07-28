'use client'

import { Settings2 } from 'lucide-react'
import {
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import ForceGraph3D, {
  type ForceGraphMethods,
} from 'react-force-graph-3d'
import { Color, Raycaster, Vector2 } from 'three'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'

import { ProjectGalaxyControlPanel } from '@/components/records/project-galaxy-control-panel'
import type { ProjectRecordGraphPreview } from '@/lib/api/types'
import { formatDateTime } from '@/lib/format'
import { GALAXY_COLOR_THEMES } from '@/lib/records/project-galaxy-color-themes'
import {
  ProjectClusterClouds,
  ProjectNebulaDome,
} from '@/lib/records/project-galaxy-nebula'
import {
  buildGalaxyFieldStars,
  buildGalaxyStarfield,
  buildStaticGalaxyLayer,
  disposeGalaxyObject,
  disposeGalaxyPoints,
  GALAXY_QUALITY_TIERS,
  GALAXY_VISUAL_PRESETS,
  type GalaxyQualityTierId,
  type GalaxyStaticLayer,
} from '@/lib/records/project-galaxy-rendering'
import {
  cloneDefaultProjectGalaxySettings,
  mergeProjectGalaxySettings,
  type ProjectGalaxySettings,
} from '@/lib/records/project-galaxy-settings'
import {
  buildProjectForceGraph,
  forceNodeId,
  layoutStaticGalaxyNodes,
  projectForceNodeHash,
  type ProjectForceLink,
  type ProjectForceNode,
} from '@/lib/records/project-force-graph'
import {
  RECORD_GRAPH_KIND_COLOR,
  RECORD_GRAPH_KIND_LABEL,
} from '@/lib/records/project-record-graph'

type ProjectGalaxyForceGraphProps = {
  preview: ProjectRecordGraphPreview
  selectedNodeId: string | null
  onSelectNode: (nodeId: string | null) => void
}

const GALAXY_RENDERER_CONFIG = {
  antialias: false,
  alpha: false,
  powerPreference: 'high-performance',
} as const

const EMPTY_FORCE_GRAPH_DATA: {
  nodes: ProjectForceNode[]
  links: ProjectForceLink[]
} = { nodes: [], links: [] }

export function ProjectGalaxyForceGraph({
  preview,
  selectedNodeId,
  onSelectNode,
}: ProjectGalaxyForceGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<ForceGraphMethods<ProjectForceNode, ProjectForceLink> | undefined>(undefined)
  const staticLayerRef = useRef<GalaxyStaticLayer | null>(null)
  const hoverCardRef = useRef<HTMLDivElement>(null)
  const hoverPositionRef = useRef({ x: 12, y: 56 })
  const hoveredNodeIdRef = useRef<string | null>(null)
  const [size, setSize] = useState({ width: 800, height: 720 })
  const [panelOpen, setPanelOpen] = useState(false)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [settings, setSettings] = useState<ProjectGalaxySettings>(
    cloneDefaultProjectGalaxySettings,
  )
  const storageKey = useMemo(() => {
    const projectNode = preview.nodes.find((node) => node.kind === 'project')
    return `opencli:project-galaxy:${projectNode?.id ?? 'default'}`
  }, [preview.nodes])
  const graphData = useMemo(() => {
    const data = buildProjectForceGraph(preview)
    const connected = settings.showOrphans
      ? null
      : new Set(data.links.flatMap((link) => [
        forceNodeId(link.source),
        forceNodeId(link.target),
      ]))
    const nodes = connected
      ? data.nodes.filter((node) => connected.has(node.id))
      : data.nodes
    return {
      nodes: layoutStaticGalaxyNodes(nodes, data.links),
      links: data.links,
    }
  }, [preview, settings.showOrphans])
  const selection = useMemo(
    () => buildSelectionScope(graphData.links, selectedNodeId, settings.selectionDepth),
    [graphData.links, selectedNodeId, settings.selectionDepth],
  )
  const hoveredNode = useMemo(
    () => graphData.nodes.find((node) => node.id === hoveredNodeId) ?? null,
    [graphData.nodes, hoveredNodeId],
  )
  const presetId = settings.preset === 'deep-space'
    ? 'deep-space'
    : 'daylight'
  const qualityId = resolveQualityTier(settings.qualityOverride)
  const preset = GALAXY_VISUAL_PRESETS[presetId]
  const quality = GALAXY_QUALITY_TIERS[qualityId]
  const colorTheme = GALAXY_COLOR_THEMES.find((theme) => theme.id === settings.colorTheme)
    ?? GALAXY_COLOR_THEMES[0]!

  useEffect(() => {
    const saved = window.localStorage.getItem(storageKey)
    if (saved) {
      try {
        setSettings(mergeProjectGalaxySettings(JSON.parse(saved)))
      } catch {
        setSettings(cloneDefaultProjectGalaxySettings())
      }
    }
  }, [storageKey])

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(settings))
  }, [settings, storageKey])

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => {
      setSize({
        width: Math.max(320, Math.floor(entry.contentRect.width)),
        height: Math.max(560, Math.floor(entry.contentRect.height)),
      })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const graph = graphRef.current
    if (!graph) return
    const layer = buildStaticGalaxyLayer({
      nodes: graphData.nodes,
      links: graphData.links,
      nodeResolution: quality.nodeResolution,
      nodeOpacity: preset.nodeOpacity,
      nodeValue: (node) => (
        galaxyNodeValue(node, settings.look.sizeBy)
        * settings.look.nodeSize
        * (
          !selectedNodeId
            ? 1
            : node.id === selectedNodeId
              ? 2.4
              : selection.nodeIds.has(node.id) ? 1.16 : 0.68
        )
      ),
      nodeColor: (node) => galaxyNodeColor(
        node,
        colorTheme.colors,
        selectedNodeId,
        selection.nodeIds,
        preset.lightMode,
      ),
      linkColor: (link) => {
        if (!selectedNodeId) return preset.linkInk ?? '#77739b'
        return selection.linkIds.has(link.id) ? '#a78bfa' : '#25252d'
      },
      linkOpacity: settings.look.linkOpacity * preset.linkOpacityScale,
    })
    staticLayerRef.current = layer
    graph.scene().add(layer.group)
    return () => {
      graph.scene().remove(layer.group)
      if (staticLayerRef.current === layer) staticLayerRef.current = null
      layer.dispose()
    }
  }, [
    colorTheme.colors,
    graphData,
    preset.linkInk,
    preset.lightMode,
    preset.linkOpacityScale,
    preset.nodeOpacity,
    quality.nodeResolution,
    selectedNodeId,
    selection.linkIds,
    selection.nodeIds,
    settings.look.linkOpacity,
    settings.look.nodeSize,
    settings.look.sizeBy,
  ])

  useEffect(() => {
    const graph = graphRef.current
    if (!graph) return
    const { group: starfield, twinkler } = buildGalaxyStarfield(1_750, quality.starScale)
    const fieldStars = buildGalaxyFieldStars(
      1_100,
      settings.space.fieldStars,
      quality.starScale,
    )
    const nebula = new ProjectNebulaDome(estimateNebulaRadius(graphData.nodes.length))
    nebula.setQuality(quality.starScale)
    nebula.bake(colorTheme.colors[0]!, colorTheme.colors[1]!)
    const rendererPixelRatio = Math.min(window.devicePixelRatio, quality.pixelRatioCap)
    graph.renderer().setPixelRatio(rendererPixelRatio)
    const camera = graph.camera()
    const cameraFov = 'fov' in camera && typeof camera.fov === 'number' ? camera.fov : 45
    const physicalHeight = size.height * rendererPixelRatio
    const pixelScale = physicalHeight / (
      2 * Math.tan((cameraFov * Math.PI) / 360)
    )
    nebula.setPixelScale(
      pixelScale,
      1_600 * rendererPixelRatio,
    )
    nebula.setIntensity(preset.space ? settings.space.nebula : 0)
    const clusterClouds = new ProjectClusterClouds()
    clusterClouds.setPixelScale(
      pixelScale,
      300 * rendererPixelRatio,
    )
    clusterClouds.setIntensity(
      preset.space && quality.clusterCloudsAllowed
        ? settings.space.clusterClouds
        : 0,
    )
    starfield.visible = preset.space && settings.showStarfield
    fieldStars.visible = preset.space && settings.space.fieldStars > 0.005
    graph.scene().add(starfield, fieldStars, nebula.object, clusterClouds.points)
    rebuildProjectClusterClouds(
      clusterClouds,
      graphData.nodes,
      colorTheme.colors,
      preset.space && quality.clusterCloudsAllowed
        ? settings.space.clusterClouds
        : 0,
    )

    let animationFrame = 0
    let previousTime = performance.now()
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const animateAtmosphere = (now: number) => {
      const deltaSeconds = Math.min((now - previousTime) / 1_000, 0.05)
      previousTime = now
      if (!document.hidden) {
        staticLayerRef.current?.update(reducedMotion ? 0 : now / 1_000)
      }
      if (!document.hidden && preset.space) {
        twinkler.update(deltaSeconds, settings.look.twinkle)
        fieldStars.rotation.y += deltaSeconds * 0.0008
        nebula.update(deltaSeconds)
      }
      animationFrame = window.requestAnimationFrame(animateAtmosphere)
    }
    animationFrame = window.requestAnimationFrame(animateAtmosphere)

    return () => {
      window.cancelAnimationFrame(animationFrame)
      graph.scene().remove(starfield, fieldStars, nebula.object, clusterClouds.points)
      disposeGalaxyObject(starfield)
      disposeGalaxyPoints(fieldStars)
      nebula.dispose()
      clusterClouds.dispose()
    }
  }, [
    preset.space,
    quality.pixelRatioCap,
    quality.starScale,
    quality.clusterCloudsAllowed,
    colorTheme,
    graphData.nodes.length,
    size.height,
    settings.look.twinkle,
    settings.showStarfield,
    settings.space.clusterClouds,
    settings.space.fieldStars,
    settings.space.nebula,
    graphData.nodes,
  ])

  useEffect(() => {
    const controls = graphRef.current?.controls() as {
      autoRotate?: boolean
      autoRotateSpeed?: number
    } | undefined
    if (!controls) return
    controls.autoRotate = settings.cruise
    controls.autoRotateSpeed = settings.cruiseSpeed
  }, [settings.cruise, settings.cruiseSpeed])

  useEffect(() => {
    const graph = graphRef.current
    if (
      !graph
      || qualityId !== 'high'
      || !preset.bloomEnabled
      || !quality.bloomAllowed
    ) return

    const bloom = new UnrealBloomPass(
      new Vector2(size.width, size.height),
      settings.bloom.strength,
      settings.bloom.radius,
      settings.bloom.threshold,
    )
    const composer = graph.postProcessingComposer()
    composer.addPass(bloom)

    return () => {
      composer.removePass(bloom)
      bloom.dispose()
    }
  }, [
    preset.bloomEnabled,
    quality.bloomAllowed,
    qualityId,
    settings.bloom.radius,
    settings.bloom.strength,
    settings.bloom.threshold,
    size.height,
    size.width,
  ])

  useEffect(() => {
    const graph = graphRef.current
    if (!graph) return
    const handleVisibility = () => {
      if (document.hidden) graph.pauseAnimation()
      else graph.resumeAnimation()
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [])

  const graphBounds = useMemo(() => {
    if (!graphData.nodes.length) {
      return { center: { x: 0, y: 0, z: 0 }, radius: 1 }
    }
    const axes = ['x', 'y', 'z'] as const
    const center = { x: 0, y: 0, z: 0 }
    axes.forEach((axis) => {
      const values = graphData.nodes.map((node) => node[axis] ?? 0)
      center[axis] = (Math.min(...values) + Math.max(...values)) / 2
    })
    const radius = graphData.nodes.reduce((largest, node) => Math.max(
      largest,
      Math.hypot(
        (node.x ?? 0) - center.x,
        (node.y ?? 0) - center.y,
        (node.z ?? 0) - center.z,
      ),
    ), 1)
    return { center, radius }
  }, [graphData.nodes])

  const fitGalaxy = useCallback(() => {
    const distance = Math.max(260, graphBounds.radius * 2.25)
    const { center } = graphBounds
    graphRef.current?.cameraPosition(
      {
        x: center.x + distance * 0.12,
        y: center.y + distance * 0.22,
        z: center.z + distance,
      },
      center,
      700,
    )
  }, [graphBounds])

  useEffect(() => {
    const timer = window.setTimeout(fitGalaxy, 120)
    return () => window.clearTimeout(timer)
  }, [fitGalaxy])

  useEffect(() => {
    const graph = graphRef.current
    if (!graph) return
    const canvas = graph.renderer().domElement
    const raycaster = new Raycaster()
    const pointer = new Vector2()
    let pointerDown: { x: number; y: number } | null = null
    let lastHoverAt = 0
    const setHoveredNode = (nodeId: string | null) => {
      if (hoveredNodeIdRef.current === nodeId) return
      hoveredNodeIdRef.current = nodeId
      setHoveredNodeId(nodeId)
    }
    const pickNode = (event: PointerEvent) => {
      const layer = staticLayerRef.current
      if (!layer) return null
      const bounds = canvas.getBoundingClientRect()
      pointer.set(
        ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
        -((event.clientY - bounds.top) / bounds.height) * 2 + 1,
      )
      raycaster.setFromCamera(pointer, graph.camera())
      const instanceId = raycaster.intersectObject(layer.nodeMesh, false)[0]?.instanceId
      return typeof instanceId === 'number' ? layer.nodeIds[instanceId] ?? null : null
    }
    const positionHoverCard = (event: PointerEvent) => {
      const bounds = containerRef.current?.getBoundingClientRect()
      if (!bounds) return
      const x = Math.max(12, Math.min(bounds.width - 364, event.clientX - bounds.left + 14))
      const y = Math.max(56, Math.min(bounds.height - 260, event.clientY - bounds.top + 14))
      hoverPositionRef.current = { x, y }
      hoverCardRef.current?.style.setProperty(
        'transform',
        `translate3d(${x}px, ${y}px, 0)`,
      )
    }
    const handlePointerMove = (event: PointerEvent) => {
      if (
        quality.hoverThrottleMs === null
        || event.pointerType === 'touch'
        || event.timeStamp - lastHoverAt < quality.hoverThrottleMs
      ) return
      lastHoverAt = event.timeStamp
      const nodeId = pickNode(event)
      canvas.style.cursor = nodeId ? 'pointer' : 'grab'
      if (nodeId) positionHoverCard(event)
      setHoveredNode(nodeId)
    }
    const handlePointerLeave = () => {
      canvas.style.cursor = ''
      setHoveredNode(null)
    }
    const handlePointerDown = (event: PointerEvent) => {
      pointerDown = { x: event.clientX, y: event.clientY }
    }
    const handlePointerUp = (event: PointerEvent) => {
      if (
        !pointerDown
        || Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 4
      ) {
        pointerDown = null
        return
      }
      pointerDown = null
      const nodeId = pickNode(event)
      setHoveredNode(null)
      onSelectNode(nodeId)
    }
    canvas.addEventListener('pointermove', handlePointerMove, { passive: true })
    canvas.addEventListener('pointerleave', handlePointerLeave, { passive: true })
    canvas.addEventListener('pointerdown', handlePointerDown, { passive: true })
    canvas.addEventListener('pointerup', handlePointerUp, { passive: true })
    return () => {
      canvas.style.cursor = ''
      canvas.removeEventListener('pointermove', handlePointerMove)
      canvas.removeEventListener('pointerleave', handlePointerLeave)
      canvas.removeEventListener('pointerdown', handlePointerDown)
      canvas.removeEventListener('pointerup', handlePointerUp)
    }
  }, [onSelectNode, quality.hoverThrottleMs])

  useEffect(() => {
    if (!hoveredNodeId) return
    const { x, y } = hoverPositionRef.current
    hoverCardRef.current?.style.setProperty(
      'transform',
      `translate3d(${x}px, ${y}px, 0)`,
    )
  }, [hoveredNodeId])

  const flyToNode = useCallback((node: ProjectForceNode) => {
    if (
      typeof node.x !== 'number'
      || typeof node.y !== 'number'
      || typeof node.z !== 'number'
    ) return
    const distance = 280
    const magnitude = Math.hypot(node.x, node.y, node.z) || 1
    graphRef.current?.cameraPosition(
      {
        x: node.x + (node.x / magnitude) * distance,
        y: node.y + (node.y / magnitude) * distance,
        z: node.z + (node.z / magnitude) * distance,
      },
      { x: node.x, y: node.y, z: node.z },
      Math.round(900 / settings.tour.speed),
    )
  }, [settings.tour.speed])

  useEffect(() => {
    if (!selectedNodeId) return
    const node = graphData.nodes.find((candidate) => candidate.id === selectedNodeId)
    if (node) flyToNode(node)
  }, [flyToNode, graphData.nodes, selectedNodeId])

  return (
    <div
      ref={containerRef}
      className="relative h-full min-h-[44rem] w-full overflow-hidden transition-colors"
      style={{ backgroundColor: preset.background }}
    >
      <div className="absolute left-3 top-3 z-20 flex flex-wrap gap-2">
        <GalaxySegmentedControl
          label="视觉"
          value={presetId}
          options={Object.values(GALAXY_VISUAL_PRESETS)}
          onChange={(value) => setSettings((current) => ({
            ...current,
            preset: value === 'daylight' ? 'adaptive' : 'deep-space',
          }))}
        />
        <GalaxySegmentedControl
          label="画质"
          value={qualityId}
          options={Object.values(GALAXY_QUALITY_TIERS)}
          onChange={(value) => setSettings((current) => ({
            ...current,
            qualityOverride: value as GalaxyQualityTierId,
          }))}
        />
        <button
          type="button"
          onClick={fitGalaxy}
          className="min-h-9 rounded-md border border-white/15 bg-black/55 px-3 text-xs text-white shadow-lg backdrop-blur hover:bg-black/70"
        >
          全图
        </button>
        <button
          type="button"
          onClick={() => setPanelOpen((open) => !open)}
          className="flex min-h-9 items-center gap-2 rounded-md border border-white/15 bg-black/55 px-3 text-xs text-white shadow-lg backdrop-blur hover:bg-black/70"
          aria-pressed={panelOpen}
        >
          <Settings2 className="size-3.5" />
          设置
        </button>
      </div>
      {panelOpen ? (
        <ProjectGalaxyControlPanel
          settings={settings}
          onChange={setSettings}
          onClose={() => setPanelOpen(false)}
          onRecenter={fitGalaxy}
          onReset={() => setSettings(cloneDefaultProjectGalaxySettings())}
        />
      ) : null}
      {hoveredNode ? (
        <GalaxyNodeHoverCard node={hoveredNode} cardRef={hoverCardRef} />
      ) : null}
      <ForceGraph3D<ProjectForceNode, ProjectForceLink>
        ref={graphRef}
        width={size.width}
        height={size.height}
        rendererConfig={GALAXY_RENDERER_CONFIG}
        graphData={EMPTY_FORCE_GRAPH_DATA}
        backgroundColor={preset.background}
        warmupTicks={0}
        cooldownTicks={0}
        enableNodeDrag={false}
        enablePointerInteraction={false}
        enableNavigationControls
        showNavInfo={false}
      />
    </div>
  )
}

function GalaxyNodeHoverCard({
  node,
  cardRef,
}: {
  node: ProjectForceNode
  cardRef: RefObject<HTMLDivElement | null>
}) {
  const summary = node.preview ?? node.subtitle
  const source = node.source_id ?? readableNodeUrl(node.url)
  const publishedAt = node.source_published_at ?? node.created_at

  return (
    <aside
      ref={cardRef}
      className="pointer-events-none absolute left-0 top-0 z-30 w-[min(22rem,calc(100%-1.5rem))] overflow-hidden rounded-xl border border-white/15 bg-[#0c0f16]/94 text-zinc-100 shadow-2xl backdrop-blur-xl will-change-transform"
      role="tooltip"
    >
      <header className="border-b border-white/10 px-4 py-3">
        <div className="flex items-center justify-between gap-3 text-[10px] uppercase tracking-[0.18em] text-zinc-400">
          <span className="flex items-center gap-2">
            <span
              className="size-2 rounded-full"
              style={{
                backgroundColor: RECORD_GRAPH_KIND_COLOR[node.kind],
                boxShadow: `0 0 10px ${RECORD_GRAPH_KIND_COLOR[node.kind]}`,
              }}
            />
            {RECORD_GRAPH_KIND_LABEL[node.kind]}
          </span>
          <span>{node.degree.toLocaleString('zh-CN')} 条关系</span>
        </div>
        <h2 className="mt-2 break-words text-sm font-semibold leading-5">
          {node.displayLabel}
        </h2>
        {summary ? (
          <p className="mt-1.5 line-clamp-3 text-xs leading-5 text-zinc-400">
            {summary}
          </p>
        ) : null}
      </header>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3 text-xs">
        <GalaxyHoverFact label="来源" value={source ?? '未标注'} />
        <GalaxyHoverFact label="状态" value={node.status ?? '可用'} />
        <GalaxyHoverFact label="源发布时间" value={formatDateTime(publishedAt)} />
        <GalaxyHoverFact label="关联计数" value={node.count.toLocaleString('zh-CN')} />
      </dl>
      <p className="truncate border-t border-white/10 px-4 py-2 font-mono text-[9px] text-zinc-600">
        {node.id}
      </p>
    </aside>
  )
}

function GalaxyHoverFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[9px] uppercase tracking-wider text-zinc-600">{label}</dt>
      <dd className="mt-1 truncate text-zinc-300" title={value}>{value}</dd>
    </div>
  )
}

function readableNodeUrl(value: string | null) {
  if (!value) return null
  try {
    return new URL(value).hostname.replace(/^www\./, '')
  } catch {
    return value
  }
}

function resolveQualityTier(
  override: ProjectGalaxySettings['qualityOverride'],
): GalaxyQualityTierId {
  if (override !== 'auto') return override
  if (typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches) {
    return 'mobile'
  }
  if (typeof window !== 'undefined' && window.devicePixelRatio > 1) return 'low'
  return 'high'
}

function galaxyNodeValue(
  node: ProjectForceNode,
  sizeBy: ProjectGalaxySettings['look']['sizeBy'],
) {
  if (sizeBy === 'uniform') return 3
  if (sizeBy === 'fileSize') return Math.min(24, 2 + Math.log1p(node.count) * 2.2)
  return node.val
}

function galaxyNodeColor(
  node: ProjectForceNode,
  colors: string[],
  selectedNodeId: string | null = null,
  selectedScope: Set<string> = new Set(),
  lightMode = false,
) {
  const index = projectForceNodeHash(node.kind) % colors.length
  const base = colors[index] ?? node.color
  if (!selectedNodeId) return base
  if (node.id === selectedNodeId) return lightMode ? '#171717' : '#ffffff'
  if (selectedScope.has(node.id)) {
    return new Color(base).lerp(new Color('#ffffff'), 0.28).getStyle()
  }
  return lightMode ? '#cfccc5' : '#10131b'
}

function estimateNebulaRadius(nodeCount: number) {
  const graphRadiusEstimate = Math.min(300, Math.max(45, Math.sqrt(nodeCount) * 30))
  return graphRadiusEstimate * 2.6
}

function rebuildProjectClusterClouds(
  clouds: ProjectClusterClouds,
  nodes: ProjectForceNode[],
  colors: string[],
  intensity: number,
) {
  const positions = new Float32Array(nodes.length * 3)
  let graphRadius = 1
  nodes.forEach((node, index) => {
    const x = node.x ?? 0
    const y = node.y ?? 0
    const z = node.z ?? 0
    positions[index * 3] = x
    positions[index * 3 + 1] = y
    positions[index * 3 + 2] = z
    graphRadius = Math.max(graphRadius, Math.hypot(x, y, z))
  })
  clouds.rebuild(nodes, positions, graphRadius)
  clouds.recolor((index) => new Color(galaxyNodeColor(nodes[index]!, colors)))
  clouds.setIntensity(intensity)
}

function buildSelectionScope(
  links: ProjectForceLink[],
  selectedNodeId: string | null,
  depth: 1 | 2,
) {
  const nodeIds = new Set<string>()
  const linkIds = new Set<string>()
  if (!selectedNodeId) return { nodeIds, linkIds }

  nodeIds.add(selectedNodeId)
  let frontier = new Set([selectedNodeId])
  for (let level = 0; level < depth; level += 1) {
    const next = new Set<string>()
    links.forEach((link) => {
      const source = forceNodeId(link.source)
      const target = forceNodeId(link.target)
      if (frontier.has(source)) {
        linkIds.add(link.id)
        nodeIds.add(target)
        next.add(target)
      }
      if (frontier.has(target)) {
        linkIds.add(link.id)
        nodeIds.add(source)
        next.add(source)
      }
    })
    frontier = next
  }
  return { nodeIds, linkIds }
}

function GalaxySegmentedControl({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: Array<{ id: string; label: string }>
  onChange: (value: string) => void
}) {
  return (
    <div
      className="flex items-center rounded-md border border-white/15 bg-black/55 p-1 text-white shadow-lg backdrop-blur"
      aria-label={label}
    >
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          aria-pressed={value === option.id}
          onClick={() => onChange(option.id)}
          className={`min-h-7 rounded px-2 text-[11px] transition-colors ${
            value === option.id ? 'bg-white/18 text-white' : 'text-zinc-400 hover:text-white'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
