'use client'

import { ArrowRight, BrainCircuit, ExternalLink, GitBranch, X } from 'lucide-react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useMemo } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import type { WorkflowEdge, WorkflowNode } from '@/lib/flow/types'
import { useSettingsStore } from '@/lib/flow/settings-store'
import { runtimeStatusLabel, runtimeStatusTone } from '@/lib/workflow/capabilities'
import { localizeNodeText } from '@/lib/workflow/node-i18n'
import { cn } from '@/lib/utils'

export type WorkflowWorkbenchMode = 'evidence'

export function WorkflowWorkbenchPanel({
  nodes,
  edges,
  onClose,
}: {
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  onClose: () => void
}) {
  const params = useSearchParams()
  const language = useSettingsStore((state) => state.language)
  const workspaceId = params.get('workspace')
  const projectId = params.get('project')
  const workflowId = params.get('workflow')
  const selectedNode = nodes.find((node) => node.selected) ?? nodes[0] ?? null
  const selectedNodeText = selectedNode
    ? localizeNodeText(
        selectedNode.data.canonical?.catalogId ?? selectedNode.data.runtimeCapability?.id ?? selectedNode.id,
        { label: selectedNode.data.label, description: selectedNode.data.description },
        language,
      )
    : null
  const usingFallback = Boolean(selectedNode && !selectedNode.selected)
  const evidencePath = useMemo(
    () => selectedNode ? upstreamPath(nodes, edges, selectedNode.id) : [],
    [edges, nodes, selectedNode],
  )
  const events = useMemo(
    () => nodes.flatMap((node) => node.data.runtimeLatestEvent ? [{ node, event: node.data.runtimeLatestEvent }] : [])
      .sort((left, right) => right.event.sequence - left.event.sequence)
      .slice(0, 10),
    [nodes],
  )
  const evidenceHref = workspaceId && projectId
    ? `/studio/projects/${projectId}/evidence?workspace=${workspaceId}${workflowId ? `&workflow=${workflowId}` : ''}`
    : null

  return (
    <aside className="workflow-floating-panel absolute bottom-3 right-3 top-3 z-40 flex w-[25rem] max-w-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-lg border bg-popover shadow-2xl" aria-label="画布工作台">
      <header className="flex items-center gap-2 border-b px-3 py-2.5">
        <span className="grid size-8 place-items-center rounded-md border bg-background">
          <BrainCircuit className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold">画布工作台</p>
          <p className="truncate text-[10px] text-muted-foreground">跟随当前选中节点 · 只读诊断</p>
        </div>
        <Button variant="ghost" size="icon" className="size-9" onClick={onClose} aria-label="关闭画布工作台"><X className="size-4" /></Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {!selectedNode ? <EmptyPanel /> : <>
          <section>
            <div className="flex items-center justify-between gap-2">
              <Badge variant="outline">{selectedNode.data.category}</Badge>
              <span className={cn('rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase', runtimeStatusTone(selectedNode.data.runtimeCapability?.status))}>{runtimeStatusLabel(selectedNode.data.runtimeCapability?.status)}</span>
            </div>
            <h2 className="mt-3 text-base font-semibold">{selectedNodeText?.label ?? selectedNode.data.label}</h2>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{selectedNodeText?.description || '该节点没有额外说明。'}{usingFallback ? ' 当前未选择节点，暂时显示流程首节点。' : ''}</p>
          </section>

          <NodeEvidenceView path={evidencePath} events={events} selectedNode={selectedNode} />
        </>}
      </div>

      <footer className="flex flex-wrap gap-2 border-t p-3">
        {evidenceHref ? <Link href={evidenceHref} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'flex-1')}><ExternalLink className="size-3.5" />完整逻辑与证据</Link> : null}
      </footer>
    </aside>
  )
}

function NodeEvidenceView({ path, events, selectedNode }: { path: WorkflowNode[]; events: Array<{ node: WorkflowNode; event: NonNullable<WorkflowNode['data']['runtimeLatestEvent']> }>; selectedNode: WorkflowNode }) {
  return <div className="mt-5 space-y-5">
    <section><SectionTitle icon={GitBranch}>上游决策路径</SectionTitle><p className="mt-1 text-[11px] leading-5 text-muted-foreground">显式展示节点和运行事实，不展示模型内部原始思维链。</p><div className="mt-3 space-y-2">{path.map((node, index) => <div key={node.id} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2"><span className="grid size-6 place-items-center rounded-full border bg-background font-mono text-[9px]">{index + 1}</span><div className={cn('rounded-md border px-3 py-2', node.id === selectedNode.id && 'border-primary/60 bg-primary/5')}><p className="truncate text-xs font-medium">{node.data.label}</p><p className="mt-1 truncate font-mono text-[10px] text-muted-foreground">{node.data.runtimeLatestEvent?.eventType ?? node.data.runtimeCapability?.status ?? 'configured'}</p></div>{index < path.length - 1 ? <ArrowRight className="ml-1 size-3 rotate-90 text-muted-foreground" /> : null}</div>)}</div></section>
    <section><SectionTitle icon={BrainCircuit}>最近运行事件</SectionTitle><div className="mt-2 space-y-2">{events.length ? events.map(({ node, event }) => <div key={event.id} className="rounded-md border p-3"><div className="flex items-center justify-between gap-2"><p className="truncate text-xs font-medium">{node.data.label}</p><Badge variant="outline">{event.eventType}</Badge></div><p className="mt-1 line-clamp-2 text-[11px] leading-5 text-muted-foreground">{event.message || `sequence ${event.sequence} · trace ${event.traceId}`}</p></div>) : <p className="rounded-md border border-dashed p-4 text-xs leading-5 text-muted-foreground">尚未产生运行事件。试运行后这里会按 sequence 展示节点事实和 trace 标识。</p>}</div></section>
  </div>
}

function SectionTitle({ children, icon: Icon }: { children: React.ReactNode; icon: typeof GitBranch }) { return <div className="flex items-center gap-2 text-xs font-medium"><Icon className="size-3.5 text-muted-foreground" />{children}</div> }
function EmptyPanel() { return <div className="grid min-h-72 place-items-center text-center"><div><GitBranch className="mx-auto size-5 text-muted-foreground" /><p className="mt-3 text-sm font-medium">画布还没有节点</p><p className="mt-1 text-xs text-muted-foreground">添加节点后可在这里检查逻辑与证据。</p></div></div> }

function upstreamPath(nodes: WorkflowNode[], edges: WorkflowEdge[], targetId: string) {
  const nodeById = new Map(nodes.map((node) => [node.id, node]))
  const incomingCount = new Map(nodes.map((node) => [node.id, 0]))
  const outgoing = new Map<string, string[]>()
  edges.forEach((edge) => {
    incomingCount.set(edge.target, (incomingCount.get(edge.target) ?? 0) + 1)
    outgoing.set(edge.source, [...(outgoing.get(edge.source) ?? []), edge.target])
  })
  const roots = nodes.filter((node) => (incomingCount.get(node.id) ?? 0) === 0).map((node) => node.id)
  const queue = roots.length ? [...roots] : nodes.slice(0, 1).map((node) => node.id)
  const parent = new Map<string, string | null>(queue.map((id) => [id, null]))
  while (queue.length) {
    const current = queue.shift() as string
    if (current === targetId) break
    for (const neighbor of outgoing.get(current) ?? []) if (!parent.has(neighbor)) { parent.set(neighbor, current); queue.push(neighbor) }
  }
  if (!parent.has(targetId)) return nodeById.get(targetId) ? [nodeById.get(targetId) as WorkflowNode] : []
  const ids: string[] = []
  for (let current: string | null = targetId; current; current = parent.get(current) ?? null) ids.unshift(current)
  return ids.flatMap((id) => nodeById.get(id) ? [nodeById.get(id) as WorkflowNode] : [])
}
