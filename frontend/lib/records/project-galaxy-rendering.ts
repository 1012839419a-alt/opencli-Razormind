import {
  BufferAttribute,
  BufferGeometry,
  Color,
  Group,
  Points,
  PointsMaterial,
} from 'three'

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
  linkSegments: number
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
    linkSegments: 8,
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
    linkSegments: 6,
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
    linkSegments: 4,
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
