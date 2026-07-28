import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Color,
  Group,
  InstancedMesh,
  LineBasicMaterial,
  LineSegments,
  MeshBasicMaterial,
  Object3D,
  Points,
  PointsMaterial,
  ShaderMaterial,
  SphereGeometry,
} from 'three'

import type {
  ProjectForceLink,
  ProjectForceNode,
} from '@/lib/records/project-force-graph'

/*
 * Direct downstream adaptation of galaxy-view rendering modules:
 * https://github.com/2233admin/galaxy-view
 * Upstream version 0.6.0, commit ca00838.
 * Copyright (c) 2026 Rick — MIT License.
 *
 * Changes are limited to OpenCLI naming, formatting, and exported product tokens.
 */

export type GalaxyVisualPresetId = 'deep-space' | 'daylight'
export type GalaxyQualityTierId = 'high' | 'low' | 'mobile'

export type GalaxyVisualPreset = {
  id: GalaxyVisualPresetId
  label: string
  background: string
  starfield: boolean
  space: boolean
  motes: boolean
  bloomEnabled: boolean
  lightMode: boolean
  nodeLightness: number | null
  linkInk: string | null
  linkOpacityScale: number
  nodeOpacity: number
}

export type GalaxyQualityTier = {
  id: GalaxyQualityTierId
  label: string
  pixelRatioCap: number
  bloomAllowed: boolean
  starScale: number
  clusterCloudsAllowed: boolean
  nodeCap: number | null
  linkCap: number | null
  hubLabels: number
  neighborLabels: number
  hoverThrottleMs: number | null
  nodeResolution: number
}

export const GALAXY_VISUAL_PRESETS: Record<GalaxyVisualPresetId, GalaxyVisualPreset> = {
  'deep-space': {
    id: 'deep-space',
    label: '深空',
    background: '#000003',
    starfield: true,
    space: true,
    motes: false,
    bloomEnabled: true,
    lightMode: false,
    nodeLightness: null,
    linkInk: null,
    linkOpacityScale: 1,
    nodeOpacity: 0.94,
  },
  daylight: {
    id: 'daylight',
    label: '晨昼',
    background: '#f6f4ef',
    starfield: false,
    space: false,
    motes: true,
    bloomEnabled: false,
    lightMode: true,
    nodeLightness: 0.44,
    linkInk: '#2e2a24',
    linkOpacityScale: 0.65,
    nodeOpacity: 0.9,
  },
}

export const GALAXY_QUALITY_TIERS: Record<GalaxyQualityTierId, GalaxyQualityTier> = {
  high: {
    id: 'high',
    label: '高画质',
    pixelRatioCap: 2,
    bloomAllowed: true,
    starScale: 1,
    clusterCloudsAllowed: true,
    nodeCap: null,
    linkCap: null,
    hubLabels: 14,
    neighborLabels: 20,
    hoverThrottleMs: 30,
    nodeResolution: 16,
  },
  low: {
    id: 'low',
    label: '流畅',
    pixelRatioCap: 1,
    bloomAllowed: true,
    starScale: 0.4,
    clusterCloudsAllowed: true,
    nodeCap: null,
    linkCap: null,
    hubLabels: 8,
    neighborLabels: 12,
    hoverThrottleMs: 80,
    nodeResolution: 10,
  },
  mobile: {
    id: 'mobile',
    label: '移动',
    pixelRatioCap: 1.5,
    bloomAllowed: false,
    starScale: 0.32,
    clusterCloudsAllowed: false,
    nodeCap: 1_500,
    linkCap: 12_000,
    hubLabels: 6,
    neighborLabels: 8,
    hoverThrottleMs: null,
    nodeResolution: 8,
  },
}

const STAR_CLASSES = [
  { count: 2_600, size: 1.2 },
  { count: 900, size: 2 },
  { count: 250, size: 3 },
]

const COOL_A = new Color('#9da8c4')
const COOL_B = new Color('#ffffff')
const WARM = new Color('#ffe9c9')
const BLUE = new Color('#bfd3ff')

export type GalaxyStaticLayer = {
  group: Group
  nodeMesh: InstancedMesh<SphereGeometry, MeshBasicMaterial>
  nodeIds: string[]
  update: (timeSeconds: number) => void
  dispose: () => void
}

export function buildStaticGalaxyLayer({
  nodes,
  links,
  nodeResolution,
  nodeOpacity,
  nodeValue,
  nodeColor,
  linkColor,
  linkOpacity,
}: {
  nodes: ProjectForceNode[]
  links: ProjectForceLink[]
  nodeResolution: number
  nodeOpacity: number
  nodeValue: (node: ProjectForceNode) => number
  nodeColor: (node: ProjectForceNode) => string
  linkColor: (link: ProjectForceLink) => string
  linkOpacity: number
}): GalaxyStaticLayer {
  const group = new Group()
  group.name = 'opencli-project-galaxy-static-layer'

  const sphere = new SphereGeometry(
    1,
    Math.max(6, nodeResolution),
    Math.max(4, Math.round(nodeResolution * 0.65)),
  )
  const nodeMaterial = new MeshBasicMaterial({
    transparent: nodeOpacity < 1,
    opacity: nodeOpacity,
  })
  const nodeMesh = new InstancedMesh(sphere, nodeMaterial, nodes.length)
  const dummy = new Object3D()
  const color = new Color()
  nodes.forEach((node, index) => {
    dummy.position.set(node.x ?? 0, node.y ?? 0, node.z ?? 0)
    dummy.scale.setScalar(Math.max(1, Math.cbrt(nodeValue(node)) * 4))
    dummy.updateMatrix()
    nodeMesh.setMatrixAt(index, dummy.matrix)
    nodeMesh.setColorAt(index, color.set(nodeColor(node)))
  })
  nodeMesh.instanceMatrix.needsUpdate = true
  if (nodeMesh.instanceColor) nodeMesh.instanceColor.needsUpdate = true
  nodeMesh.computeBoundingSphere()
  nodeMesh.name = 'opencli-project-galaxy-nodes'

  const positions = new Float32Array(links.length * 6)
  const colors = new Float32Array(links.length * 6)
  const particlePositions = new Float32Array(links.length * 2 * 3)
  const particleTargets = new Float32Array(links.length * 2 * 3)
  const particlePhases = new Float32Array(links.length * 2)
  const particleColors = new Float32Array(links.length * 2 * 3)
  const nodesById = new Map(nodes.map((node) => [node.id, node]))
  let visibleLinks = 0
  links.forEach((link) => {
    const sourceId = typeof link.source === 'string' ? link.source : link.source.id
    const targetId = typeof link.target === 'string' ? link.target : link.target.id
    const source = nodesById.get(sourceId)
    const target = nodesById.get(targetId)
    if (!source || !target) return
    const offset = visibleLinks * 6
    positions.set([
      source.x ?? 0,
      source.y ?? 0,
      source.z ?? 0,
      target.x ?? 0,
      target.y ?? 0,
      target.z ?? 0,
    ], offset)
    color.set(linkColor(link))
    colors.set([color.r, color.g, color.b, color.r, color.g, color.b], offset)
    for (let particleIndex = 0; particleIndex < 2; particleIndex += 1) {
      const particleOffset = (visibleLinks * 2 + particleIndex) * 3
      particlePositions.set([
        source.x ?? 0,
        source.y ?? 0,
        source.z ?? 0,
      ], particleOffset)
      particleTargets.set([
        target.x ?? 0,
        target.y ?? 0,
        target.z ?? 0,
      ], particleOffset)
      particleColors.set([color.r, color.g, color.b], particleOffset)
      particlePhases[visibleLinks * 2 + particleIndex] = (
        projectGalaxyHash(link.id) / 4294967296 + particleIndex * 0.5
      ) % 1
    }
    visibleLinks += 1
  })
  const linkGeometry = new BufferGeometry()
  linkGeometry.setAttribute('position', new BufferAttribute(positions, 3))
  linkGeometry.setAttribute('color', new BufferAttribute(colors, 3))
  linkGeometry.setDrawRange(0, visibleLinks * 2)
  linkGeometry.computeBoundingSphere()
  const linkMaterial = new LineBasicMaterial({
    transparent: true,
    opacity: linkOpacity,
    vertexColors: true,
    depthWrite: false,
  })
  const linkLines = new LineSegments(linkGeometry, linkMaterial)
  linkLines.name = 'opencli-project-galaxy-links'
  linkLines.renderOrder = -0.5

  const particleGeometry = new BufferGeometry()
  particleGeometry.setAttribute('position', new BufferAttribute(particlePositions, 3))
  particleGeometry.setAttribute('target', new BufferAttribute(particleTargets, 3))
  particleGeometry.setAttribute('phase', new BufferAttribute(particlePhases, 1))
  particleGeometry.setAttribute('color', new BufferAttribute(particleColors, 3))
  particleGeometry.setDrawRange(0, visibleLinks * 2)
  const particleMaterial = new ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uOpacity: { value: Math.min(0.92, 0.48 + linkOpacity) },
    },
    vertexShader: `
      attribute vec3 target;
      attribute float phase;
      attribute vec3 color;
      varying vec3 vColor;
      uniform float uTime;

      void main() {
        float progress = fract(uTime * 0.085 + phase);
        vec3 point = mix(position, target, smoothstep(0.0, 1.0, progress));
        vec4 viewPoint = modelViewMatrix * vec4(point, 1.0);
        gl_Position = projectionMatrix * viewPoint;
        gl_PointSize = clamp(560.0 / max(1.0, -viewPoint.z), 1.6, 5.5);
        vColor = color;
      }
    `,
    fragmentShader: `
      varying vec3 vColor;
      uniform float uOpacity;

      void main() {
        float distanceToCenter = length(gl_PointCoord - vec2(0.5));
        float alpha = smoothstep(0.5, 0.08, distanceToCenter) * uOpacity;
        gl_FragColor = vec4(vColor, alpha);
      }
    `,
  })
  const linkParticles = new Points(particleGeometry, particleMaterial)
  linkParticles.name = 'opencli-project-galaxy-link-particles'
  linkParticles.renderOrder = 0.5
  linkParticles.frustumCulled = false

  group.add(linkLines, linkParticles, nodeMesh)
  return {
    group,
    nodeMesh,
    nodeIds: nodes.map((node) => node.id),
    update: (timeSeconds) => {
      particleMaterial.uniforms.uTime!.value = timeSeconds
    },
    dispose: () => {
      sphere.dispose()
      nodeMaterial.dispose()
      linkGeometry.dispose()
      linkMaterial.dispose()
      particleGeometry.dispose()
      particleMaterial.dispose()
    },
  }
}

function projectGalaxyHash(value: string) {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

export class GalaxyTwinkler {
  private readonly baseColors: Float32Array
  private readonly attribute: BufferAttribute
  private active: { index: number; elapsed: number } | null = null
  private nextIn = 3

  constructor(
    geometry: BufferGeometry,
    private readonly starCount: number,
  ) {
    this.attribute = geometry.getAttribute('color') as BufferAttribute
    this.baseColors = new Float32Array(this.attribute.array as Float32Array)
  }

  update(deltaSeconds: number, frequency: number) {
    if (this.active) {
      this.active.elapsed += deltaSeconds
      const duration = 1.6
      const colors = this.attribute.array as Float32Array
      const offset = this.active.index * 3
      const multiplier = this.active.elapsed >= duration
        ? 1
        : 1 + 2.2 * Math.sin((Math.PI * this.active.elapsed) / duration)
      colors[offset] = (this.baseColors[offset] ?? 1) * multiplier
      colors[offset + 1] = (this.baseColors[offset + 1] ?? 1) * multiplier
      colors[offset + 2] = (this.baseColors[offset + 2] ?? 1) * multiplier
      this.attribute.needsUpdate = true
      if (this.active.elapsed >= duration) this.active = null
      return
    }
    if (frequency <= 0.01) return
    this.nextIn -= deltaSeconds
    if (this.nextIn <= 0) {
      this.active = { index: Math.floor(Math.random() * this.starCount), elapsed: 0 }
      this.nextIn = Math.min(
        Math.max(-Math.log(Math.random() + 1e-9) * (6 / frequency), 1.5),
        90,
      )
    }
  }
}

export function buildGalaxyStarfield(shellRadius: number, scale = 1) {
  const group = new Group()
  const random = mulberry32(0x517cc1)
  let twinkler: GalaxyTwinkler | null = null

  for (const base of STAR_CLASSES) {
    const count = Math.max(Math.round(base.count * scale), 50)
    const positions = new Float32Array(count * 3)
    const colors = new Float32Array(count * 3)
    for (let index = 0; index < count; index += 1) {
      const theta = Math.PI * 2 * random()
      const phi = Math.acos(2 * random() - 1)
      const radius = shellRadius * (0.95 + 0.1 * random())
      positions[index * 3] = radius * Math.sin(phi) * Math.cos(theta)
      positions[index * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta)
      positions[index * 3 + 2] = radius * Math.cos(phi)

      const pick = random()
      const color = pick < 0.85
        ? COOL_A.clone().lerp(COOL_B, random())
        : pick < 0.95 ? WARM.clone() : BLUE.clone()
      if (base.size >= 3 && random() < 0.03) color.multiplyScalar(1.8)
      colors[index * 3] = color.r
      colors[index * 3 + 1] = color.g
      colors[index * 3 + 2] = color.b
    }
    const geometry = new BufferGeometry()
    geometry.setAttribute('position', new BufferAttribute(positions, 3))
    geometry.setAttribute('color', new BufferAttribute(colors, 3))
    const material = new PointsMaterial({
      size: base.size,
      sizeAttenuation: false,
      vertexColors: true,
      transparent: true,
      opacity: 0.55,
      depthWrite: false,
    })
    const points = new Points(geometry, material)
    points.renderOrder = -1
    group.add(points)
    if (base.size >= 3) twinkler = new GalaxyTwinkler(geometry, count)
  }

  group.name = 'opencli-project-galaxy-starfield'
  return {
    group,
    twinkler: twinkler ?? createFallbackTwinkler(),
  }
}

export function buildGalaxyFieldStars(
  volumeRadius: number,
  density: number,
  scale = 1,
) {
  const count = Math.max(Math.round(1_200 * density * scale), 1)
  const random = mulberry32(0x2f6e1b)
  const positions = new Float32Array(count * 3)
  const colors = new Float32Array(count * 3)
  for (let index = 0; index < count; index += 1) {
    const radius = volumeRadius * (0.3 + 0.7 * Math.cbrt(random()))
    const theta = Math.PI * 2 * random()
    const phi = Math.acos(2 * random() - 1)
    positions[index * 3] = radius * Math.sin(phi) * Math.cos(theta)
    positions[index * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta)
    positions[index * 3 + 2] = radius * Math.cos(phi)
    const pick = random()
    const color = (pick < 0.85
      ? COOL_A.clone().lerp(COOL_B, random())
      : pick < 0.95 ? WARM.clone() : BLUE.clone()).multiplyScalar(0.75)
    colors[index * 3] = color.r
    colors[index * 3 + 1] = color.g
    colors[index * 3 + 2] = color.b
  }
  const geometry = new BufferGeometry()
  geometry.setAttribute('position', new BufferAttribute(positions, 3))
  geometry.setAttribute('color', new BufferAttribute(colors, 3))
  const material = new PointsMaterial({
    size: 2.4,
    sizeAttenuation: true,
    vertexColors: true,
    transparent: true,
    opacity: 0.6,
    depthWrite: false,
  })
  const points = new Points(geometry, material)
  points.name = 'opencli-project-galaxy-field-stars'
  points.renderOrder = -1
  points.frustumCulled = false
  return points
}

export function disposeGalaxyObject(group: Group) {
  group.traverse((object) => {
    if (!(object instanceof Points)) return
    object.geometry.dispose()
    if (Array.isArray(object.material)) {
      object.material.forEach((material) => material.dispose())
    } else {
      object.material.dispose()
    }
  })
}

export function disposeGalaxyPoints(points: Points<BufferGeometry, PointsMaterial>) {
  points.geometry.dispose()
  points.material.dispose()
}

function createFallbackTwinkler() {
  const geometry = new BufferGeometry()
  geometry.setAttribute('color', new BufferAttribute(new Float32Array(3), 3))
  return new GalaxyTwinkler(geometry, 1)
}

function mulberry32(seed: number) {
  let value = seed >>> 0
  return () => {
    value = (value + 0x6d2b79f5) >>> 0
    let next = value
    next = Math.imul(next ^ (next >>> 15), next | 1)
    next ^= next + Math.imul(next ^ (next >>> 7), next | 61)
    return ((next ^ (next >>> 14)) >>> 0) / 4294967296
  }
}
