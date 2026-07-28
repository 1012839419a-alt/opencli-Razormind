/*
 * Direct copy of galaxy-view/src/render/colorThemes.ts.
 * Copyright (c) 2026 Rick — MIT License.
 */

export interface GalaxyColorTheme {
  id: string
  name: string
  colors: string[]
}

export const GALAXY_COLOR_THEMES: GalaxyColorTheme[] = [
  {
    id: 'hubble',
    name: '哈勃深空',
    colors: ['#46d4dc', '#ffc35c', '#d05a32', '#7fd0a0', '#e8d9a0', '#5a9bd8', '#d87fa8', '#9a7fe0', '#cfd8e8'],
  },
  {
    id: 'tiktok',
    name: '抖音霓虹',
    colors: ['#25f4ee', '#fe2c55', '#ffffff', '#7ae8e2', '#ff7a9c', '#19b8b2', '#c2244a', '#a8f0ec', '#ffd0dc'],
  },
  {
    id: 'sunset',
    name: '落日胶片',
    colors: ['#f58529', '#dd2a7b', '#8134af', '#515bd4', '#feda77', '#e1306c', '#c13584', '#fd8d32', '#405de6'],
  },
  {
    id: 'cyber',
    name: '赛博都市',
    colors: ['#fcee0a', '#00f0ff', '#ff003c', '#9d00ff', '#00ff9f', '#ff6ec7', '#3df5ff', '#ffe600', '#c800ff'],
  },
  {
    id: 'matrix',
    name: '黑客帝国',
    colors: ['#00ff41', '#33ff66', '#00cc34', '#66ff8c', '#00b32d', '#80ffa0', '#1aff4d', '#00e639', '#4dff79'],
  },
  {
    id: 'aurora',
    name: '极光',
    colors: ['#1db954', '#00d4ff', '#7f5fff', '#38f0c0', '#4fa8ff', '#9f7fff', '#22e6a8', '#66c2ff', '#b08fff'],
  },
]
