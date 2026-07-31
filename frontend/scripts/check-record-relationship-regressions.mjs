import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { registerHooks, stripTypeScriptTypes } from 'node:module'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

registerHooks({
  resolve(specifier, context, nextResolve) {
    const candidates = []
    if (specifier.startsWith('@/')) {
      candidates.push(path.join(frontendRoot, specifier.slice(2)))
    } else if (specifier.startsWith('.') && context.parentURL?.startsWith('file:')) {
      candidates.push(path.resolve(path.dirname(fileURLToPath(context.parentURL)), specifier))
    }
    for (const candidate of candidates) {
      for (const resolvedPath of [candidate, `${candidate}.ts`, `${candidate}.tsx`]) {
        if (existsSync(resolvedPath)) {
          return { url: pathToFileURL(resolvedPath).href, shortCircuit: true }
        }
      }
    }
    return nextResolve(specifier, context)
  },
  load(url, context, nextLoad) {
    if (url.endsWith('.ts') || url.endsWith('.tsx')) {
      const source = stripTypeScriptTypes(readFileSync(fileURLToPath(url), 'utf8'), {
        mode: 'strip',
        sourceUrl: url,
      })
      return { format: 'module', source, shortCircuit: true }
    }
    return nextLoad(url, context)
  },
})

const read = (relativePath) => readFile(path.join(frontendRoot, relativePath), 'utf8')

function preview() {
  return {
    workspace_id: 'workspace-1',
    project_id: 'project-1',
    project_name: '项目一',
    strategy: 'server-aggregated-sample',
    truncated: true,
    max_nodes: 300,
    nodes: [
      {
        id: 'project:project-1',
        kind: 'project',
        label: '项目一',
        subtitle: '项目预览',
        count: 100_000,
      },
      {
        id: 'workflow:workflow-1',
        kind: 'workflow',
        label: '采集工作流',
        subtitle: '主工作流',
        count: 100_000,
      },
      {
        id: 'record:record-1',
        kind: 'record',
        label: '第一条消息',
        subtitle: 'example.test',
        count: 1,
        record_id: 'record-1',
      },
      {
        id: 'entity:tag:climate',
        kind: 'entity',
        label: 'climate',
        subtitle: '标签',
        count: 42,
      },
    ],
    edges: [
      {
        id: 'contains:1',
        source: 'project:project-1',
        target: 'workflow:workflow-1',
        kind: 'contains',
        label: '项目归属',
        weight: 100_000,
        bidirectional: true,
      },
      {
        id: 'semantic:1',
        source: 'record:record-1',
        target: 'entity:tag:climate',
        kind: 'semantic',
        label: '语义双链',
        weight: 1,
        bidirectional: true,
      },
    ],
    stats: {
      total_records: 100_000,
      sampled_records: 200,
      hidden_records: 99_800,
      total_sources: 18,
      total_workflows: 1,
      total_runs: 40,
      visible_nodes: 4,
      visible_edges: 2,
    },
    generated_at: '2026-07-18T08:00:00Z',
  }
}

test('project preview becomes an undirected WebGL graph with aggregate node sizing', async () => {
  const { buildProjectRecordGraph } = await import(
    pathToFileURL(path.join(frontendRoot, 'lib/records/project-record-graph.ts')).href
  )

  const graph = buildProjectRecordGraph(preview())
  assert.equal(graph.order, 4)
  assert.equal(graph.size, 2)
  assert.equal(graph.type, 'undirected')
  assert.ok(
    graph.getNodeAttribute('project:project-1', 'size') >
      graph.getNodeAttribute('record:record-1', 'size'),
  )
  assert.equal(
    graph.getEdgeAttribute('semantic:1', 'graphEdge').bidirectional,
    true,
  )
})

test('records graph is project-scoped, bounded and rendered through a client-only Sigma island', async () => {
  const [tabs, page, canvas, endpoints, hooks] = await Promise.all([
    read('components/shell/route-tabs.tsx'),
    read('app/(app)/records/graph/page.tsx'),
    read('components/records/project-record-graph-canvas.tsx'),
    read('lib/api/endpoints.ts'),
    read('lib/api/hooks.ts'),
  ])

  assert.match(tabs, /href: '\/records\/graph', label: '关系图谱'/)
  assert.match(page, /useWorkspaceProjects/)
  assert.match(page, /useProjectRecordGraph/)
  assert.match(page, /ssr: false/)
  assert.match(page, /服务端聚合预览/)
  assert.match(page, /隐藏 .* 条，避免图谱过载/)
  assert.match(canvas, /SigmaContainer/)
  assert.match(canvas, /FA2Layout/)
  assert.match(canvas, /barnesHutOptimize/)
  assert.match(canvas, /layout\.kill\(\)/)
  assert.match(endpoints, /projects\/\$\{projectId\}\/record-graph/)
  assert.match(hooks, /\['project-record-graph'/)
})

test('project data surface distinguishes source freshness from ingestion time', async () => {
  const [dataPage, types] = await Promise.all([
    read('app/(app)/studio/projects/[projectId]/data/page.tsx'),
    read('lib/api/types.ts'),
  ])

  assert.match(types, /source_published_at: string \| null/)
  assert.match(dataPage, /源发布时间/)
  assert.doesNotMatch(dataPage, /<TableHead>更新时间<\/TableHead>/)
  assert.doesNotMatch(dataPage, /formatRelative\(record\.updated_at\)/)
})

test('project evidence opens the recovered 3D Galaxy and keeps a 2D relationship view', async () => {
  const [
    evidencePage,
    galaxyPage,
    relationshipPage,
    explorer,
    galaxy,
    galaxyRendering,
    galaxyControls,
    navigation,
  ] = await Promise.all([
    read('app/(app)/studio/projects/[projectId]/evidence/page.tsx'),
    read('app/(app)/studio/projects/[projectId]/galaxy/page.tsx'),
    read('app/(app)/studio/projects/[projectId]/relationships/page.tsx'),
    read('components/records/project-graph-explorer.tsx'),
    read('components/records/project-galaxy-force-graph.tsx'),
    read('lib/records/project-galaxy-rendering.ts'),
    read('components/records/project-galaxy-control-panel.tsx'),
    read('components/studio/project-navigation.tsx'),
  ])

  assert.match(evidencePage, /mode="galaxy"/)
  assert.match(galaxyPage, /mode="galaxy"/)
  assert.match(relationshipPage, /mode="relationships"/)
  assert.match(explorer, /ProjectGalaxyForceGraph/)
  assert.match(explorer, /ProjectRelationshipForceGraph/)
  assert.match(galaxy, /ForceGraph3D/)
  assert.match(galaxy, /cameraPosition/)
  assert.match(galaxy, /rendererConfig=\{GALAXY_RENDERER_CONFIG\}/)
  assert.match(galaxy, /powerPreference: 'high-performance'/)
  assert.match(galaxy, /antialias: false/)
  assert.match(galaxy, /window\.devicePixelRatio > 1/)
  assert.match(galaxy, /graphData=\{EMPTY_FORCE_GRAPH_DATA\}/)
  assert.match(galaxy, /cooldownTicks=\{0\}/)
  assert.match(galaxy, /warmupTicks=\{0\}/)
  assert.match(galaxy, /enableNodeDrag=\{false\}/)
  assert.match(galaxy, /enablePointerInteraction=\{false\}/)
  assert.doesNotMatch(galaxy, /d3Force|d3ReheatSimulation/)
  assert.match(galaxy, /selection\.nodeIds\.has\(node\.id\) \? 1\.16 : 0\.68/)
  assert.match(galaxy, /selectedScope\.has\(node\.id\)/)
  assert.match(galaxyRendering, /new InstancedMesh/)
  assert.match(galaxyRendering, /new LineSegments/)
  assert.match(galaxyRendering, /opencli-project-galaxy-link-particles/)
  assert.match(galaxyRendering, /uTime/)
  assert.match(galaxy, /staticLayerRef\.current\?\.update/)
  assert.match(galaxy, /handlePointerMove/)
  assert.match(galaxy, /quality\.hoverThrottleMs/)
  assert.match(galaxy, /GalaxyNodeHoverCard/)
  assert.match(galaxy, /源发布时间/)
  assert.match(galaxy, /node\.preview \?\? node\.subtitle/)
  assert.match(galaxy, /UnrealBloomPass/)
  assert.match(galaxy, /postProcessingComposer/)
  assert.match(galaxy, /qualityId !== 'high'/)
  assert.match(galaxyControls, /qualityOverride/)
  assert.match(galaxyControls, /value: 'auto', label: '自动'/)
  assert.match(galaxyControls, /光晕强度/)
  assert.match(galaxyControls, /深空高画质启用/)
  assert.doesNotMatch(galaxyControls, /布局与物理|排斥力|链接强度|中心引力/)
  assert.match(galaxyControls, /恢复全部默认值/)
  assert.match(navigation, /label: '逻辑与证据'/)
  assert.match(navigation, /label: '证据关系'/)
  assert.doesNotMatch(navigation, /label: 'Galaxy'/)
})

test('Galaxy freezes a deterministic relationship-driven 3D layout', async () => {
  const { buildProjectForceGraph, layoutStaticGalaxyNodes } = await import(
    pathToFileURL(path.join(frontendRoot, 'lib/records/project-force-graph.ts')).href
  )

  const topology = {
    ...preview(),
    nodes: [
      { id: 'project:p', kind: 'project', label: 'P', count: 10 },
      { id: 'workflow:a', kind: 'workflow', label: 'A', count: 5 },
      { id: 'workflow:b', kind: 'workflow', label: 'B', count: 5 },
      { id: 'source:a', kind: 'source', label: 'SA', count: 2 },
      { id: 'source:b', kind: 'source', label: 'SB', count: 2 },
      { id: 'record:a1', kind: 'record', label: 'A1', count: 1 },
      { id: 'record:a2', kind: 'record', label: 'A2', count: 1 },
      { id: 'record:b1', kind: 'record', label: 'B1', count: 1 },
      { id: 'record:b2', kind: 'record', label: 'B2', count: 1 },
      { id: 'entity:bridge', kind: 'entity', label: 'Bridge', count: 2 },
      { id: 'record:orphan', kind: 'record', label: 'Orphan', count: 1 },
    ],
    edges: [
      { id: 'p-a', source: 'project:p', target: 'workflow:a', kind: 'contains', weight: 5 },
      { id: 'p-b', source: 'project:p', target: 'workflow:b', kind: 'contains', weight: 5 },
      { id: 'a-sa', source: 'workflow:a', target: 'source:a', kind: 'produced', weight: 2 },
      { id: 'b-sb', source: 'workflow:b', target: 'source:b', kind: 'produced', weight: 2 },
      { id: 'sa-a1', source: 'source:a', target: 'record:a1', kind: 'origin', weight: 1 },
      { id: 'sa-a2', source: 'source:a', target: 'record:a2', kind: 'origin', weight: 1 },
      { id: 'sb-b1', source: 'source:b', target: 'record:b1', kind: 'origin', weight: 1 },
      { id: 'sb-b2', source: 'source:b', target: 'record:b2', kind: 'origin', weight: 1 },
      { id: 'a1-e', source: 'record:a1', target: 'entity:bridge', kind: 'semantic', weight: 1 },
      { id: 'b1-e', source: 'record:b1', target: 'entity:bridge', kind: 'semantic', weight: 1 },
    ].map((edge) => ({ ...edge, label: edge.kind, bidirectional: true })),
  }
  const first = buildProjectForceGraph(topology)
  const second = buildProjectForceGraph(topology)
  layoutStaticGalaxyNodes(first.nodes, first.links)
  layoutStaticGalaxyNodes(second.nodes, second.links)

  assert.deepEqual(
    first.nodes.map(({ id, x, y, z, fx, fy, fz }) => ({ id, x, y, z, fx, fy, fz })),
    second.nodes.map(({ id, x, y, z, fx, fy, fz }) => ({ id, x, y, z, fx, fy, fz })),
  )
  assert.ok(first.nodes.every((node) => (
    Number.isFinite(node.x)
    && node.x === node.fx
    && node.y === node.fy
    && node.z === node.fz
  )))

  const byId = new Map(first.nodes.map((node) => [node.id, node]))
  const distance = (left, right) => Math.hypot(
    left.x - right.x,
    left.y - right.y,
    left.z - right.z,
  )
  assert.ok(
    distance(byId.get('record:a1'), byId.get('source:a'))
      < distance(byId.get('record:a1'), byId.get('source:b')),
  )
  assert.ok(
    distance(byId.get('record:a1'), byId.get('record:a2'))
      < distance(byId.get('record:a1'), byId.get('record:b2')),
  )
  assert.ok(
    distance(byId.get('source:a'), byId.get('source:b'))
      > distance(byId.get('record:a1'), byId.get('source:a')) * 2,
  )
  const bridge = byId.get('entity:bridge')
  const bridgeMidpoint = {
    x: (byId.get('record:a1').x + byId.get('record:b1').x) / 2,
    y: (byId.get('record:a1').y + byId.get('record:b1').y) / 2,
    z: (byId.get('record:a1').z + byId.get('record:b1').z) / 2,
  }
  assert.ok(
    distance(bridge, bridgeMidpoint)
      < distance(byId.get('record:a1'), byId.get('record:b1')) * 0.25,
  )
  assert.ok(
    Math.hypot(
      byId.get('record:orphan').x,
      byId.get('record:orphan').y,
      byId.get('record:orphan').z,
    ) > 350,
  )

  const volume = Array.from({ length: 96 }, (_, index) => ({
    ...first.nodes[index % first.nodes.length],
    id: `volume:${index}`,
    kind: index % 3 === 0 ? 'entity' : 'record',
  }))
  layoutStaticGalaxyNodes(volume, [])
  const span = (axis) => {
    const values = volume.map((node) => node[axis])
    return Math.max(...values) - Math.min(...values)
  }
  const spans = [span('x'), span('y'), span('z')]
  assert.ok(Math.min(...spans) > Math.max(...spans) * 0.45)
})
