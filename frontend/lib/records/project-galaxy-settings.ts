/*
 * Direct downstream adaptation of galaxy-view/src/settings.ts.
 * https://github.com/2233admin/galaxy-view
 * Copyright (c) 2026 Rick — MIT License.
 *
 * Obsidian persistence fields are replaced with browser-local project view settings.
 */

export interface GalaxyBloomSettings {
  strength: number
  radius: number
  threshold: number
}

export type GalaxySizeBy = 'degree' | 'fileSize' | 'uniform'

export interface GalaxyLookSettings {
  nodeSize: number
  linkOpacity: number
  twinkle: number
  sizeBy: GalaxySizeBy
}

export interface GalaxySpaceSettings {
  nebula: number
  fieldStars: number
  clusterClouds: number
}

export interface ProjectGalaxySettings {
  bloom: GalaxyBloomSettings
  look: GalaxyLookSettings
  space: GalaxySpaceSettings
  cruise: boolean
  cruiseSpeed: number
  showOrphans: boolean
  showStarfield: boolean
  colorTheme: string
  qualityOverride: 'auto' | 'high' | 'low' | 'mobile'
  preset: 'deep-space' | 'adaptive'
  selectionDepth: 1 | 2
  panelWidth: number
  tour: { speed: number }
}

export const DEFAULT_PROJECT_GALAXY_SETTINGS: ProjectGalaxySettings = {
  bloom: { strength: 0.35, radius: 0.35, threshold: 0.22 },
  look: {
    nodeSize: 1,
    linkOpacity: 0.14,
    twinkle: 0.5,
    sizeBy: 'degree',
  },
  space: {
    nebula: 0.35,
    fieldStars: 0.25,
    clusterClouds: 0.3,
  },
  cruise: true,
  cruiseSpeed: 1,
  showOrphans: true,
  showStarfield: true,
  colorTheme: 'hubble',
  qualityOverride: 'auto',
  preset: 'deep-space',
  selectionDepth: 1,
  panelWidth: 300,
  tour: { speed: 1 },
}

export function cloneDefaultProjectGalaxySettings(): ProjectGalaxySettings {
  return structuredClone(DEFAULT_PROJECT_GALAXY_SETTINGS)
}

export function mergeProjectGalaxySettings(saved: unknown): ProjectGalaxySettings {
  const defaults = DEFAULT_PROJECT_GALAXY_SETTINGS
  const value = isObject(saved) ? saved : {}
  const bloom = isObject(value.bloom) ? value.bloom : {}
  const look = isObject(value.look) ? value.look : {}
  const space = isObject(value.space) ? value.space : {}
  const tour = isObject(value.tour) ? value.tour : {}
  const number = (candidate: unknown, fallback: number) => (
    typeof candidate === 'number' && Number.isFinite(candidate) ? candidate : fallback
  )

  return {
    bloom: {
      strength: number(bloom.strength, defaults.bloom.strength),
      radius: number(bloom.radius, defaults.bloom.radius),
      threshold: number(bloom.threshold, defaults.bloom.threshold),
    },
    look: {
      nodeSize: number(look.nodeSize, defaults.look.nodeSize),
      linkOpacity: number(look.linkOpacity, defaults.look.linkOpacity),
      twinkle: number(look.twinkle, defaults.look.twinkle),
      sizeBy: ['degree', 'fileSize', 'uniform'].includes(String(look.sizeBy))
        ? look.sizeBy as GalaxySizeBy
        : defaults.look.sizeBy,
    },
    space: {
      nebula: number(space.nebula, defaults.space.nebula),
      fieldStars: number(space.fieldStars, defaults.space.fieldStars),
      clusterClouds: number(space.clusterClouds, defaults.space.clusterClouds),
    },
    cruise: typeof value.cruise === 'boolean' ? value.cruise : defaults.cruise,
    cruiseSpeed: number(value.cruiseSpeed, defaults.cruiseSpeed),
    showOrphans: typeof value.showOrphans === 'boolean'
      ? value.showOrphans
      : defaults.showOrphans,
    showStarfield: typeof value.showStarfield === 'boolean'
      ? value.showStarfield
      : defaults.showStarfield,
    colorTheme: typeof value.colorTheme === 'string'
      ? value.colorTheme
      : defaults.colorTheme,
    qualityOverride: ['auto', 'high', 'low', 'mobile'].includes(String(value.qualityOverride))
      ? value.qualityOverride as ProjectGalaxySettings['qualityOverride']
      : defaults.qualityOverride,
    preset: value.preset === 'adaptive' ? 'adaptive' : 'deep-space',
    selectionDepth: value.selectionDepth === 2 ? 2 : 1,
    panelWidth: Math.min(Math.max(number(value.panelWidth, defaults.panelWidth), 280), 420),
    tour: { speed: number(tour.speed, defaults.tour.speed) },
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
