import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Color,
  Points,
  ShaderMaterial,
} from 'three'

/*
 * Direct downstream adaptation of galaxy-view/src/render/nebula.ts.
 * Copyright (c) 2026 Rick — MIT License.
 */

const NEBULA_VERTEX = `
attribute float aSize;
attribute vec3 aColor;
varying vec3 vColor;
uniform float uPixelScale;
uniform float uMaxPoint;
void main() {
  vColor = aColor;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = min(aSize * uPixelScale / max(-mv.z, 1.0), uMaxPoint);
  gl_Position = projectionMatrix * mv;
}
`

const NEBULA_FRAGMENT = `
varying vec3 vColor;
uniform float uIntensity;
void main() {
  float r = length(gl_PointCoord - 0.5) * 2.0;
  float a = exp(-r * r * 2.6) - 0.0743;
  if (a < 0.003) discard;
  gl_FragColor = vec4(vColor * uIntensity * 0.30, a * uIntensity * 0.22);
}
`

const CLOUD_VERTEX = `
attribute float aSize;
varying vec3 vColor;
uniform float uPixelScale;
uniform float uMaxPoint;
void main() {
  vColor = color;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = min(aSize * uPixelScale / max(-mv.z, 1.0), uMaxPoint);
  gl_Position = projectionMatrix * mv;
}
`

const CLOUD_FRAGMENT = `
varying vec3 vColor;
uniform float uIntensity;
void main() {
  vec2 uv = gl_PointCoord - 0.5;
  float d2 = dot(uv, uv);
  float a = exp(-d2 * 10.0) - 0.0821;
  if (a < 0.004) discard;
  gl_FragColor = vec4(vColor * uIntensity * 0.55, a * uIntensity * 0.4);
}
`

const NEBULA_CENTERS = 6
const SPRITES_PER_CENTER = 24
const NEBULA_MAX = NEBULA_CENTERS * SPRITES_PER_CENTER
const MAX_CLUSTERS = 10
const POINTS_PER_CLUSTER = 3

export class ProjectNebulaDome {
  readonly object: Points<BufferGeometry, ShaderMaterial>
  private scale = 1
  private count = 0

  constructor(private readonly radius: number) {
    const geometry = new BufferGeometry()
    geometry.setAttribute('position', new BufferAttribute(new Float32Array(NEBULA_MAX * 3), 3))
    geometry.setAttribute('aColor', new BufferAttribute(new Float32Array(NEBULA_MAX * 3), 3))
    geometry.setAttribute('aSize', new BufferAttribute(new Float32Array(NEBULA_MAX), 1))
    geometry.setDrawRange(0, 0)
    const material = new ShaderMaterial({
      vertexShader: NEBULA_VERTEX,
      fragmentShader: NEBULA_FRAGMENT,
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
      uniforms: {
        uPixelScale: { value: 1 },
        uMaxPoint: { value: 1_600 },
        uIntensity: { value: 0 },
      },
    })
    this.object = new Points(geometry, material)
    this.object.renderOrder = -1
    this.object.frustumCulled = false
  }

  setQuality(scale: number) {
    this.scale = scale
  }

  bake(tintHexA: string, tintHexB: string) {
    const random = seededRandom(0x9e37)
    const positionAttribute = this.object.geometry.getAttribute('position') as BufferAttribute
    const colorAttribute = this.object.geometry.getAttribute('aColor') as BufferAttribute
    const sizeAttribute = this.object.geometry.getAttribute('aSize') as BufferAttribute
    const positions = positionAttribute.array as Float32Array
    const colors = colorAttribute.array as Float32Array
    const sizes = sizeAttribute.array as Float32Array
    const first = new Color(tintHexA)
    const second = new Color(tintHexB)
    const hsl = { h: 0, s: 0, l: 0 }
    const color = new Color()
    const centers = Math.max(2, Math.round(NEBULA_CENTERS * this.scale))
    const sprites = Math.max(6, Math.round(SPRITES_PER_CENTER * this.scale))
    let point = 0
    for (let center = 0; center < centers && point < NEBULA_MAX; center += 1) {
      const theta = Math.PI * 2 * random()
      const phi = Math.acos(2 * random() - 1)
      const centerRadius = this.radius * (0.7 + 1.7 * random())
      const centerX = centerRadius * Math.sin(phi) * Math.cos(theta)
      const centerY = centerRadius * Math.sin(phi) * Math.sin(theta) * 0.75
      const centerZ = centerRadius * Math.cos(phi)
      const spread = this.radius * (0.5 + 0.5 * random())
      color.copy(first).lerp(second, random())
      color.getHSL(hsl)
      color.setHSL(
        hsl.h + (random() - 0.5) * 0.05,
        Math.min(hsl.s * 0.85, 0.9),
        0.16 + 0.08 * random(),
      )
      for (let index = 0; index < sprites && point < NEBULA_MAX; index += 1) {
        positions[point * 3] = centerX + (random() + random() + random() - 1.5) * spread
        positions[point * 3 + 1] = centerY
          + (random() + random() + random() - 1.5) * spread * 0.8
        positions[point * 3 + 2] = centerZ
          + (random() + random() + random() - 1.5) * spread
        const large = random() < 0.25
        sizes[point] = this.radius * (large ? 1 + 0.8 * random() : 0.4 + 0.5 * random())
        const jitter = 0.85 + 0.3 * random()
        colors[point * 3] = color.r * jitter
        colors[point * 3 + 1] = color.g * jitter
        colors[point * 3 + 2] = color.b * jitter
        point += 1
      }
    }
    this.count = point
    positionAttribute.needsUpdate = true
    colorAttribute.needsUpdate = true
    sizeAttribute.needsUpdate = true
    this.object.geometry.setDrawRange(0, point)
  }

  setPixelScale(pixelScale: number, maxPointPixels: number) {
    this.object.material.uniforms.uPixelScale!.value = pixelScale
    this.object.material.uniforms.uMaxPoint!.value = maxPointPixels
  }

  setIntensity(intensity: number) {
    this.object.material.uniforms.uIntensity!.value = intensity
    this.object.visible = intensity > 0.005 && this.count > 0
  }

  update(deltaSeconds: number) {
    this.object.rotation.y += 0.0004 * deltaSeconds
  }

  dispose() {
    this.object.geometry.dispose()
    this.object.material.dispose()
  }
}

export class ProjectClusterClouds {
  readonly points: Points<BufferGeometry, ShaderMaterial>
  private memberSamples: number[][] = []
  private count = 0

  constructor() {
    const geometry = new BufferGeometry()
    geometry.setAttribute('position', new BufferAttribute(
      new Float32Array(MAX_CLUSTERS * POINTS_PER_CLUSTER * 3),
      3,
    ))
    geometry.setAttribute('color', new BufferAttribute(
      new Float32Array(MAX_CLUSTERS * POINTS_PER_CLUSTER * 3),
      3,
    ))
    geometry.setAttribute('aSize', new BufferAttribute(
      new Float32Array(MAX_CLUSTERS * POINTS_PER_CLUSTER),
      1,
    ))
    geometry.setDrawRange(0, 0)
    const material = new ShaderMaterial({
      vertexShader: CLOUD_VERTEX,
      fragmentShader: CLOUD_FRAGMENT,
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
      uniforms: {
        uPixelScale: { value: 1 },
        uMaxPoint: { value: 300 },
        uIntensity: { value: 0 },
      },
    })
    this.points = new Points(geometry, material)
    this.points.renderOrder = -1
    this.points.frustumCulled = false
  }

  rebuild(nodes: Array<{ degree: number }>, positions: Float32Array, graphRadius: number) {
    this.memberSamples = []
    if (nodes.length < 20) {
      this.count = 0
      this.points.geometry.setDrawRange(0, 0)
      return
    }
    const order = Array.from({ length: nodes.length }, (_, index) => index)
      .sort((left, right) => (nodes[right]?.degree ?? 0) - (nodes[left]?.degree ?? 0))
    const seeds: number[] = []
    const minimumGap = graphRadius * 0.5
    for (const candidate of order.slice(0, 250)) {
      const candidateX = positions[candidate * 3] ?? 0
      const candidateY = positions[candidate * 3 + 1] ?? 0
      const candidateZ = positions[candidate * 3 + 2] ?? 0
      const accepted = seeds.every((seed) => Math.hypot(
        candidateX - (positions[seed * 3] ?? 0),
        candidateY - (positions[seed * 3 + 1] ?? 0),
        candidateZ - (positions[seed * 3 + 2] ?? 0),
      ) >= minimumGap)
      if (accepted) seeds.push(candidate)
      if (seeds.length >= MAX_CLUSTERS) break
    }
    const positionAttribute = this.points.geometry.getAttribute('position') as BufferAttribute
    const sizeAttribute = this.points.geometry.getAttribute('aSize') as BufferAttribute
    const outputPositions = positionAttribute.array as Float32Array
    const outputSizes = sizeAttribute.array as Float32Array
    const memberRadius = graphRadius * 0.33
    let point = 0
    let hashSeed = 11
    for (const seed of seeds) {
      const seedX = positions[seed * 3] ?? 0
      const seedY = positions[seed * 3 + 1] ?? 0
      const seedZ = positions[seed * 3 + 2] ?? 0
      const members: number[] = []
      let meanX = 0
      let meanY = 0
      let meanZ = 0
      for (let index = 0; index < nodes.length; index += 1) {
        const deltaX = (positions[index * 3] ?? 0) - seedX
        const deltaY = (positions[index * 3 + 1] ?? 0) - seedY
        const deltaZ = (positions[index * 3 + 2] ?? 0) - seedZ
        if (deltaX ** 2 + deltaY ** 2 + deltaZ ** 2 < memberRadius ** 2) {
          members.push(index)
          meanX += positions[index * 3] ?? 0
          meanY += positions[index * 3 + 1] ?? 0
          meanZ += positions[index * 3 + 2] ?? 0
        }
      }
      if (members.length < 8) continue
      meanX /= members.length
      meanY /= members.length
      meanZ /= members.length
      const spread = Math.sqrt(members.reduce((sum, index) => sum
        + ((positions[index * 3] ?? 0) - meanX) ** 2
        + ((positions[index * 3 + 1] ?? 0) - meanY) ** 2
        + ((positions[index * 3 + 2] ?? 0) - meanZ) ** 2, 0) / members.length)
      const sample = members.length > 120
        ? members.filter((_, index) => index % Math.ceil(members.length / 120) === 0)
        : members
      for (let index = 0; index < POINTS_PER_CLUSTER; index += 1) {
        outputPositions[point * 3] = meanX + (hash2(hashSeed, index, 3) - 0.5) * spread
        outputPositions[point * 3 + 1] = meanY
          + (hash2(hashSeed, index, 5) - 0.5) * spread * 0.7
        outputPositions[point * 3 + 2] = meanZ
          + (hash2(hashSeed, index, 7) - 0.5) * spread
        outputSizes[point] = spread * (1.6 + 0.8 * hash2(hashSeed, index, 13))
        this.memberSamples.push(sample)
        point += 1
      }
      hashSeed += 1
    }
    this.count = point
    positionAttribute.needsUpdate = true
    sizeAttribute.needsUpdate = true
    this.points.geometry.setDrawRange(0, point)
  }

  recolor(colorOf: (nodeIndex: number) => Color) {
    if (this.count === 0) return
    const colorAttribute = this.points.geometry.getAttribute('color') as BufferAttribute
    const outputColors = colorAttribute.array as Float32Array
    const hsl = { h: 0, s: 0, l: 0 }
    const accumulated = new Color()
    for (let point = 0; point < this.count; point += 1) {
      const sample = this.memberSamples[point] ?? []
      accumulated.setRGB(0, 0, 0)
      sample.forEach((index) => accumulated.add(colorOf(index)))
      if (sample.length) accumulated.multiplyScalar(1 / sample.length)
      accumulated.getHSL(hsl)
      accumulated.setHSL(hsl.h, Math.min(hsl.s * 1.25, 1), 0.4)
      outputColors[point * 3] = accumulated.r
      outputColors[point * 3 + 1] = accumulated.g
      outputColors[point * 3 + 2] = accumulated.b
    }
    colorAttribute.needsUpdate = true
  }

  setIntensity(intensity: number) {
    this.points.material.uniforms.uIntensity!.value = intensity
    this.points.visible = intensity > 0.005 && this.count > 0
  }

  setPixelScale(pixelScale: number, maxPointPixels: number) {
    this.points.material.uniforms.uPixelScale!.value = pixelScale
    this.points.material.uniforms.uMaxPoint!.value = maxPointPixels
  }

  dispose() {
    this.points.geometry.dispose()
    this.points.material.dispose()
  }
}

function hash2(x: number, y: number, seed: number) {
  let hash = (x * 374761393 + y * 668265263 + seed * 1442695) | 0
  hash = Math.imul(hash ^ (hash >>> 13), 1274126177)
  return ((hash ^ (hash >>> 16)) >>> 0) / 4294967296
}

function seededRandom(seed: number) {
  let value = seed >>> 0
  return () => {
    value = (value + 0x6d2b79f5) >>> 0
    let next = value
    next = Math.imul(next ^ (next >>> 15), next | 1)
    next ^= next + Math.imul(next ^ (next >>> 7), next | 61)
    return ((next ^ (next >>> 14)) >>> 0) / 4294967296
  }
}
