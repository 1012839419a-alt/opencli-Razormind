'use client'

import { Settings2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph3D, {
  type ForceGraphMethods,
} from 'react-force-graph-3d'
import { Color, Vector2 } from 'three'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'

import { ProjectGalaxyControlPanel } from '@/components/records/project-galaxy-control-panel'
import type { ProjectRecordGraphPreview } from '@/lib/api/types'
import { GALAXY_COLOR_THEMES } from '@/lib/records/project-galaxy-color-themes'
import {
  ProjectClusterClouds,
  ProjectNebulaDome,
} from '@/lib/records/project-galaxy-nebula'
import {
  buildGalaxyFieldStars,
  buildGalaxyStarfield,
  disposeGalaxyObject,
  disposeGalaxyPoints,
  GALAXY_QUALITY_TIERS,
  GALAXY_VISUAL_PRESETS,
  type GalaxyQualityTierId,
} from '@/lib/records/project-galaxy-rendering'
import {
  cloneDefaultProjectGalaxySettings,
  mergeProjectGalaxySettings,
  type ProjectGalaxySettings,
} from '@/lib/records/project-galaxy-settings'
import {
  buildProjectForceGraph,
  forceNodeId,
  projectForceNodeTooltip,
  type ProjectForceLink,
  type ProjectForceNode,
} from '@/lib/records/project-force-graph'

type ProjectGalaxyForceGraphProps = {
  preview: ProjectRecordGraphPreview
  selectedNodeId: string | null
  onSelectNode: (nodeId: string | null) => void
}

export function ProjectGalaxyForceGraph({
  preview,
  selectedNodeId,
  onSelectNode,
}: ProjectGalaxyForceGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<ForceGraphMethods<ProjectForceNode, ProjectForceLink> | undefined>(undefined)
  const clusterCloudsRef = useRef<ProjectClusterClouds | null>(null)
  const [size, setSize] = useState({ width: 800, height: 720 })
  const [panelOpen, setPanelOpen] = useState(false)
  const [settings, setSettings] = useState<ProjectGalaxySettings>(
    cloneDefaultProjectGalaxySettings,
  )
  const storageKey = useMemo(() => {
    const projectNode = preview.nodes.find((node) => node.kind === 'project')
    return `opencli:project-galaxy:${projectNode?.id ?? 'default'}`
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
  const selection = useMemo(
    () => buildSelectionScope(graphData.links, selectedNodeId, settings.selectionDepth),
    [graphData.links, selectedNodeId, settings.selectionDepth],
  )
  const presetId = settings.preset === 'deep-space'
    ? 'deep-space'
    : 'daylight'
  const qualityId = resolveQualityTier(settings.qualityOverride)
  const preset = GALAXY_VISUAL_PRESETS[presetId]
  const quality = GALAXY_QUALITY_TIERS[qualityId]
  const physics = settings.physics
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
    const charge = graph.d3Force('charge')
    if (charge && 'strength' in charge && typeof charge.strength === 'function') {
      charge.strength(-physics.repel)
    }
    const link = graph.d3Force('link')
    if (link && 'distance' in link && typeof link.distance === 'function') {
      link.distance(physics.linkDistance)
    }
    if (link && 'strength' in link && typeof link.strength === 'function') {
      link.strength(physics.linkStrength)
    }
    graph.d3Force(
      'opencli-galaxy-structure',
      createGalaxyStructureForce(physics),
    )
    graph.d3ReheatSimulation()
    const fitTimer = window.setTimeout(() => graph.zoomToFit(800, 80), 550)
    return () => {
      window.clearTimeout(fitTimer)
      graph.d3Force('opencli-galaxy-structure', null)
    }
  }, [
    graphData,
    physics,
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
    clusterCloudsRef.current = clusterClouds
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
    const animateAtmosphere = (now: number) => {
      const deltaSeconds = Math.min((now - previousTime) / 1_000, 0.05)
      previousTime = now
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
      if (clusterCloudsRef.current === clusterClouds) clusterCloudsRef.current = null
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
    if (!graph || !preset.bloomEnabled || !quality.bloomAllowed) return

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

  const flyToNode = useCallback((node: ProjectForceNode) => {
    if (
      typeof node.x !== 'number'
      || typeof node.y !== 'number'
      || typeof node.z !== 'number'
    ) return
    const distance = 115
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

  const rebuildClusterClouds = useCallback(() => {
    const clouds = clusterCloudsRef.current
    if (!clouds || !graphData.nodes.length) return
    rebuildProjectClusterClouds(
      clouds,
      graphData.nodes,
      colorTheme.colors,
      preset.space && quality.clusterCloudsAllowed
        ? settings.space.clusterClouds
        : 0,
    )
  }, [
    colorTheme.colors,
    graphData.nodes,
    preset.space,
    quality.clusterCloudsAllowed,
    settings.space.clusterClouds,
  ])

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
          onClick={() => graphRef.current?.zoomToFit(700, 80)}
          className="min-h-9 rounded-md border border-ops-line bg-ops-panel/90 px-3 text-xs text-zinc-100 shadow-panel backdrop-blur hover:bg-ops-raised"
        >
          全图
        </button>
        <button
          type="button"
          onClick={() => setPanelOpen((open) => !open)}
          className="flex min-h-9 items-center gap-2 rounded-md border border-ops-line bg-ops-panel/90 px-3 text-xs text-zinc-100 shadow-panel backdrop-blur hover:bg-ops-raised"
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
          onRecenter={() => graphRef.current?.zoomToFit(700, 80)}
          onReset={() => setSettings(cloneDefaultProjectGalaxySettings())}
        />
      ) : null}
      <ForceGraph3D<ProjectForceNode, ProjectForceLink>
        ref={graphRef}
        width={size.width}
        height={size.height}
        graphData={graphData}
        backgroundColor={preset.background}
        nodeId="id"
        nodeVal={(node) => (
          galaxyNodeValue(node, settings.look.sizeBy)
          * settings.look.nodeSize
          * (node.id === selectedNodeId ? 1.8 : 1)
        )}
        nodeColor={(node) => galaxyNodeColor(node, colorTheme.colors)}
        nodeOpacity={preset.nodeOpacity}
        nodeResolution={quality.nodeResolution}
        nodeLabel={projectForceNodeTooltip}
        linkColor={(link) => {
          if (!selectedNodeId) {
            return preset.linkInk ?? 'rgba(120, 119, 160, 0.38)'
          }
          return selection.linkIds.has(link.id) ? '#a78bfa' : 'rgba(39, 39, 42, 0.1)'
        }}
        linkWidth={(link) => {
          if (!selectedNodeId) return Math.min(1.2, 0.16 + Math.log1p(link.weight) * 0.18)
          return selection.linkIds.has(link.id) ? 1.5 : 0.12
        }}
        linkOpacity={settings.look.linkOpacity * preset.linkOpacityScale}
        linkCurvature={(link) => link.bidirectional ? settings.look.linkCurve : 0}
        linkDirectionalParticles={(link) => (
          selectedNodeId && selection.linkIds.has(link.id) ? 2 : 0
        )}
        linkDirectionalParticleWidth={1.4}
        linkDirectionalParticleSpeed={0.004}
        cooldownTicks={180}
        d3VelocityDecay={0.26}
        enableNodeDrag
        enableNavigationControls
        showNavInfo={false}
        onNodeClick={(node) => onSelectNode(node.id)}
        onBackgroundClick={() => onSelectNode(null)}
        onEngineStop={rebuildClusterClouds}
      />
    </div>
  )
}

function resolveQualityTier(
  override: ProjectGalaxySettings['qualityOverride'],
): GalaxyQualityTierId {
  if (override !== 'auto') return override
  if (typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches) {
    return 'mobile'
  }
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

function galaxyNodeColor(node: ProjectForceNode, colors: string[]) {
  const index = hashString(node.kind) % colors.length
  return colors[index] ?? node.color
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

function createGalaxyStructureForce(
  physics: ProjectGalaxySettings['physics'],
) {
  let nodes: ProjectForceNode[] = []
  const force = ((alpha: number) => {
    nodes.forEach((node) => {
      const x = node.x ?? 0
      const y = node.y ?? 0
      const z = node.z ?? 0
      const planarRadius = Math.hypot(x, y) || 1
      const radius = Math.hypot(x, y, z) || 1
      const centerStrength = physics.centerPull * alpha * 0.015
      const coreStrength = physics.coreGravity * alpha * 0.12
      const flattenStrength = physics.flatten * alpha * 0.08
      const spiralStrength = physics.spiral * alpha

      node.vx = (node.vx ?? 0)
        - x * centerStrength
        - (x / radius) * coreStrength
        - (y / planarRadius) * spiralStrength
      node.vy = (node.vy ?? 0)
        - y * centerStrength
        - (y / radius) * coreStrength
        + (x / planarRadius) * spiralStrength
      node.vz = (node.vz ?? 0)
        - z * centerStrength
        - (z / radius) * coreStrength
        - z * flattenStrength
    })
  }) as ((alpha: number) => void) & {
    initialize: (nextNodes: ProjectForceNode[]) => void
  }
  force.initialize = (nextNodes) => {
    nodes = nextNodes
  }
  return force
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

function hashString(value: string) {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
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
      className="flex items-center rounded-md border border-ops-line bg-ops-panel/90 p-1 text-zinc-100 shadow-panel backdrop-blur"
      aria-label={label}
    >
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          aria-pressed={value === option.id}
          onClick={() => onChange(option.id)}
          className={`min-h-7 rounded px-2 text-2xs transition-colors ${
            value === option.id ? 'bg-muted text-zinc-100' : 'text-zinc-400 hover:text-zinc-100'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
