'use client'

import dynamic from 'next/dynamic'
import {
  ArrowLeft,
  Focus,
  Network,
  Orbit,
  Search,
  Sparkles,
} from 'lucide-react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useMemo, useState } from 'react'

import { GpuSurface } from '@/components/gpu/gpu-surface'
import { EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { ProjectNavigation } from '@/components/studio/project-navigation'
import { Badge } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  useProjectRecordGraph,
  useProjectWorkflows,
  useWorkspaceProjects,
} from '@/lib/api/hooks'
import type { ProjectRecordGraphPreview, RecordGraphNode } from '@/lib/api/types'
import {
  RECORD_GRAPH_KIND_COLOR,
  RECORD_GRAPH_KIND_LABEL,
  withoutRecordGraphNodeKinds,
} from '@/lib/records/project-record-graph'
import { cn } from '@/lib/utils'

const ProjectRelationshipForceGraph = dynamic(
  () => import('@/components/records/project-relationship-force-graph')
    .then((module) => module.ProjectRelationshipForceGraph),
  {
    ssr: false,
    loading: () => <GraphLoading label="正在启动 2D 力导向关系图…" />,
  },
)

const ProjectGalaxyForceGraph = dynamic(
  () => import('@/components/records/project-galaxy-force-graph')
    .then((module) => module.ProjectGalaxyForceGraph),
  {
    ssr: false,
    loading: () => <GraphLoading label="正在点亮项目星图…" />,
  },
)

const DENSITY_OPTIONS = [
  { value: 300, label: '概览 · 300 节点' },
  { value: 700, label: '标准 · 700 节点' },
  { value: 1200, label: '深入 · 1,200 节点' },
]

export function ProjectGraphExplorer({
  projectId,
  mode,
}: {
  projectId: string
  mode: 'relationships' | 'galaxy'
}) {
  const searchParams = useSearchParams()
  const workspaceId = searchParams.get('workspace')
  const preferredWorkflowId = searchParams.get('workflow')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [maxNodes, setMaxNodes] = useState(mode === 'galaxy' ? 1200 : 700)

  const projectsQuery = useWorkspaceProjects(workspaceId)
  const workflowsQuery = useProjectWorkflows(workspaceId, projectId)
  const graphQuery = useProjectRecordGraph(workspaceId, projectId, maxNodes)
  const project = projectsQuery.data?.find((candidate) => candidate.id === projectId)
  const workflowId = preferredWorkflowId
    ?? project?.primary_workflow_id
    ?? workflowsQuery.data?.[0]?.id
    ?? null
  const preview = graphQuery.data
  const isGalaxy = mode === 'galaxy'
  const graphPreview = useMemo(() => {
    if (!preview) return null
    // A collection run is operational lineage, not an evidence relationship.
    // Keep it in the API projection and operations/data surfaces, but do not
    // put it in this 2D evidence graph.
    return isGalaxy
      ? preview
      : withoutRecordGraphNodeKinds(preview, ['run'])
  }, [isGalaxy, preview])
  const selectedNode = graphPreview?.nodes.find((node) => node.id === selectedNodeId) ?? null
  const related = useMemo(
    () => graphPreview && selectedNodeId
      ? graphPreview.edges.filter((edge) => edge.source === selectedNodeId || edge.target === selectedNodeId)
      : [],
    [graphPreview, selectedNodeId],
  )
  const searchResults = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term || !graphPreview) return []
    return graphPreview.nodes
      .filter((node) => `${node.label} ${node.subtitle ?? ''} ${node.preview ?? ''}`
        .toLowerCase()
        .includes(term))
      .sort((left, right) => right.count - left.count)
      .slice(0, 12)
  }, [graphPreview, search])

  const context = workspaceId
    ? `?workspace=${workspaceId}${workflowId ? `&workflow=${workflowId}` : ''}`
    : ''
  const overviewHref = workspaceId
    ? `/studio/projects/${projectId}?workspace=${workspaceId}`
    : '/studio'
  const relationshipsHref = `/studio/projects/${projectId}/relationships${context}`
  const galaxyHref = `/studio/projects/${projectId}/galaxy${context}`
  const loading = projectsQuery.isLoading || workflowsQuery.isLoading || graphQuery.isLoading
  const error = projectsQuery.error || workflowsQuery.error || graphQuery.error

  return (
    <PageContainer
      eyebrow={isGalaxy ? 'Project galaxy' : 'Project relationships'}
      title={project
        ? `${project.name} · ${isGalaxy ? 'Galaxy 星图' : '证据关系'}`
        : isGalaxy ? '项目 Galaxy 星图' : '项目证据关系'}
      description={isGalaxy
        ? '在三维空间探索项目、工作流、运行、来源、记录与实体之间的关系。'
        : '只展示数据源、记录和实体之间的证据关系；采集运行保留在运行记录中。'}
      className="max-w-none"
      actions={(
        <Link
          href={overviewHref}
          className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'min-h-11')}
        >
          <ArrowLeft className="size-4" />
          返回项目
        </Link>
      )}
    >
      <div className="border-b pb-3">
        <ProjectNavigation
          active={isGalaxy ? 'relationships' : mode}
          workspaceId={workspaceId}
          projectId={projectId}
          workflowId={workflowId}
        />
      </div>

      <section className="overflow-hidden rounded-xl border bg-card">
        <header className="border-b bg-background/85">
          <div className="flex flex-wrap items-center justify-between gap-3 px-3 pt-3">
            <div className="flex rounded-lg border bg-muted/30 p-1" aria-label="项目图谱页面">
              <Link
                href={relationshipsHref}
                aria-current={!isGalaxy ? 'page' : undefined}
                className={graphTabClass(!isGalaxy)}
              >
                <Network className="size-3.5" />
                证据关系
              </Link>
              <Link
                href={galaxyHref}
                aria-current={isGalaxy ? 'page' : undefined}
                className={graphTabClass(isGalaxy)}
              >
                <Orbit className="size-3.5" />
                Galaxy
              </Link>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {isGalaxy ? <Sparkles className="size-3.5" /> : <Focus className="size-3.5" />}
              {isGalaxy ? '拖拽旋转 · 滚轮缩放 · 点击飞行' : '拖拽节点 · 空白平移 · 滚轮缩放'}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 p-3">
            <div className="relative min-w-64 flex-1 xl:max-w-md">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索记录、来源、实体或运行…"
                className="pl-9"
              />
              {search.trim() && searchResults.length ? (
                <div className="absolute left-0 top-11 z-40 w-full overflow-hidden rounded-lg border bg-popover shadow-xl">
                  {searchResults.map((node) => (
                    <button
                      key={node.id}
                      type="button"
                      onClick={() => {
                        setSelectedNodeId(node.id)
                        setSearch('')
                      }}
                      className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-muted"
                    >
                      <span className="truncate">{node.label}</span>
                      <span className="text-[10px] text-muted-foreground">
                        {RECORD_GRAPH_KIND_LABEL[node.kind]}
                      </span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            <Select
              value={String(maxNodes)}
              onValueChange={(value) => {
                setMaxNodes(Number(value))
                setSelectedNodeId(null)
              }}
            >
              <SelectTrigger className="w-48">
                {/* Base UI's SelectValue shows the raw value string unless told
                    how to format it — see the note on the schedule-agent Select
                    in schedule-form-dialog.tsx. `value` here is the stringified
                    `String(maxNodes)`, so match it against the stringified
                    DENSITY_OPTIONS.value (a number) rather than comparing raw. */}
                <SelectValue>
                  {(value: string | null) =>
                    DENSITY_OPTIONS.find((option) => String(option.value) === value)?.label
                      ?? '选择密度'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {DENSITY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={String(option.value)}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </header>

        {loading ? (
          <div className="p-5"><LoadingState rows={8} /></div>
        ) : error ? (
          <div className="p-5">
            <ErrorState
              message={error instanceof Error ? error.message : '项目关系图读取失败'}
              hint="确认项目已有可读取的工作流和运行记录。"
            />
          </div>
        ) : !graphPreview ? (
          <EmptyState
            title="暂无项目关系图"
            description="项目运行产生记录后，系统会建立来源、运行、记录和实体之间的关系。"
          />
        ) : (
          <div className="relative min-h-[44rem]">
            {isGalaxy ? (
              <GpuSurface
                surface="project-galaxy-graph"
                className="min-h-[44rem]"
                fallback={(
                  <ProjectGraphFallback
                    preview={preview}
                    selectedNodeId={selectedNodeId}
                    onSelectNode={setSelectedNodeId}
                  />
                )}
              >
                <ProjectGalaxyForceGraph
                  preview={graphPreview}
                  selectedNodeId={selectedNodeId}
                  onSelectNode={setSelectedNodeId}
                />
              </GpuSurface>
            ) : (
              <div
                className="min-h-[44rem]"
                data-gpu-surface="project-relationships-graph"
                data-gpu-backend="canvas2d"
              >
                <ProjectRelationshipForceGraph
                  preview={graphPreview}
                  selectedNodeId={selectedNodeId}
                  onSelectNode={setSelectedNodeId}
                />
              </div>
            )}
            {selectedNode ? (
              <GraphInspector
                node={selectedNode}
                relatedCount={related.length}
              />
            ) : null}
          </div>
        )}
      </section>
    </PageContainer>
  )
}

function ProjectGraphFallback({
  preview,
  selectedNodeId,
  onSelectNode,
}: {
  preview: ProjectRecordGraphPreview
  selectedNodeId: string | null
  onSelectNode: (nodeId: string | null) => void
}) {
  const initialNodes = preview.nodes.slice(0, 200)

  return (
    <div
      className="min-h-[44rem] overflow-y-auto bg-muted/20 p-4"
      data-project-graph-fallback
    >
      <div className="rounded-lg border bg-background p-4">
        <h2 className="text-sm font-semibold">GPU 图谱不可用</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          当前显示前 200 个节点；可使用上方搜索定位其余节点，并查看关联详情。
        </p>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {initialNodes.map((node) => (
          <button
            key={node.id}
            type="button"
            aria-pressed={selectedNodeId === node.id}
            onClick={() => onSelectNode(node.id)}
            className={cn(
              'rounded-lg border bg-background p-3 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              selectedNodeId === node.id && 'border-primary bg-primary/5',
            )}
          >
            <span className="flex items-center gap-2 text-xs text-muted-foreground">
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: RECORD_GRAPH_KIND_COLOR[node.kind] }}
              />
              {RECORD_GRAPH_KIND_LABEL[node.kind]}
            </span>
            <span className="mt-2 block break-words text-sm font-medium">{node.label}</span>
            <span className="mt-1 block text-xs text-muted-foreground">
              {node.count.toLocaleString('zh-CN')} 条关联数据
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

function GraphInspector({
  node,
  relatedCount,
}: {
  node: RecordGraphNode
  relatedCount: number
}) {
  return (
    <aside className="absolute bottom-4 right-4 z-20 w-[min(22rem,calc(100%-2rem))] overflow-hidden rounded-xl border bg-background/92 shadow-2xl backdrop-blur-xl">
      <header className="border-b p-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span
            className="size-2.5 rounded-full"
            style={{ backgroundColor: RECORD_GRAPH_KIND_COLOR[node.kind] }}
          />
          {RECORD_GRAPH_KIND_LABEL[node.kind]}
        </div>
        <h2 className="mt-3 break-words text-base font-semibold leading-6">{node.label}</h2>
        <p className="mt-1.5 line-clamp-3 text-xs leading-5 text-muted-foreground">
          {node.preview ?? node.subtitle ?? '该节点没有额外预览内容。'}
        </p>
      </header>
      <dl className="grid grid-cols-2 gap-2 border-b p-3">
        <GraphFact label="直接关系" value={relatedCount} />
        <GraphFact label="关联计数" value={node.count} />
      </dl>
      <div className="flex items-center justify-between gap-3 p-3">
        <Badge variant="outline">{node.status ?? '可用'}</Badge>
        <p className="truncate font-mono text-[9px] text-muted-foreground">
          {node.id}
        </p>
      </div>
    </aside>
  )
}

function GraphFact({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border bg-muted/15 p-3">
      <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-lg font-semibold">{value.toLocaleString('zh-CN')}</dd>
    </div>
  )
}

function GraphLoading({ label }: { label: string }) {
  return (
    <div className="grid min-h-[44rem] place-items-center bg-[#08090c] text-sm text-zinc-400">
      {label}
    </div>
  )
}

function graphTabClass(active: boolean) {
  return cn(
    'flex min-h-9 items-center gap-2 rounded-md px-3 text-xs transition-colors',
    active
      ? 'bg-background font-medium text-foreground shadow-sm'
      : 'text-muted-foreground hover:text-foreground',
  )
}
