'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Building2, FolderKanban, Link2 } from 'lucide-react'
import { toast } from 'sonner'

import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { AUTOMATION_TABS, RouteTabs } from '@/components/shell/route-tabs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  useCreateProjectSourceBinding,
  useGovernedWorkspaces,
  useGovernedWorkspaceProjects,
  useProjectSourceBindings,
  useWorkspaceSources,
} from '@/lib/api/hooks'
import type { WorkspaceSource } from '@/lib/api/types'
import { formatRelative } from '@/lib/format'

const STATUS_LABEL = {
  active: '活跃',
  disabled: '停用',
  revoked: '已撤销',
} as const

function SourceStatusBadge({ status }: { status: WorkspaceSource['status'] }) {
  return (
    <Badge
      variant={status === 'revoked' ? 'destructive' : 'secondary'}
      className={status === 'active' ? 'bg-success/10 text-success' : undefined}
    >
      {STATUS_LABEL[status]}
    </Badge>
  )
}

function bindingSlug(source: WorkspaceSource) {
  const base = source.name
    .normalize('NFKD')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'source'
  return `${base.slice(0, 91)}-${source.id.slice(0, 8)}`
}

export default function SourcesPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const workspaces = useGovernedWorkspaces()
  const [workspaceId, setWorkspaceId] = useState<string | null>(searchParams.get('workspace'))
  const projects = useGovernedWorkspaceProjects(workspaceId)
  const [projectId, setProjectId] = useState<string | null>(searchParams.get('project'))
  const sources = useWorkspaceSources(workspaceId)
  const bindings = useProjectSourceBindings(workspaceId, projectId)
  const createBinding = useCreateProjectSourceBinding()

  useEffect(() => {
    if (!workspaces.data?.length) return
    if (workspaceId && workspaces.data.some((workspace) => workspace.id === workspaceId)) return
    setWorkspaceId(workspaces.data[0].id)
  }, [workspaceId, workspaces.data])

  useEffect(() => {
    if (!projects.data) return
    if (!projects.data.length) {
      setProjectId(null)
      return
    }
    if (projectId && projects.data.some((project) => project.id === projectId)) return
    setProjectId(projects.data[0].id)
  }, [projectId, projects.data])

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString())
    if (workspaceId) params.set('workspace', workspaceId)
    else params.delete('workspace')
    if (projectId) params.set('project', projectId)
    else params.delete('project')
    const query = params.toString()
    if (query !== searchParams.toString()) router.replace(query ? `/sources?${query}` : '/sources')
  }, [projectId, router, searchParams, workspaceId])

  const selectedWorkspace = workspaces.data?.find((workspace) => workspace.id === workspaceId)
  const selectedProject = projects.data?.find((project) => project.id === projectId)
  const sourceById = useMemo(
    () => new Map((sources.data ?? []).map((source) => [source.id, source])),
    [sources.data],
  )
  const boundSourceIds = useMemo(
    () => new Set((bindings.data ?? []).map((binding) => binding.source_id)),
    [bindings.data],
  )

  async function bindSource(source: WorkspaceSource) {
    if (!workspaceId || !projectId) return
    try {
      await createBinding.mutateAsync({
        workspaceId,
        projectId,
        data: {
          source_id: source.id,
          name: source.name,
          slug: bindingSlug(source),
          source_revision_number: source.current_revision_number,
          scope_config: {},
        },
      })
      toast.success(`已将“${source.name}”绑定到 ${selectedProject?.name ?? '项目'}`)
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : '绑定 Source 失败')
    }
  }

  const error = workspaces.error ?? projects.error ?? sources.error ?? bindings.error
  const isLoading = workspaces.isLoading
    || (!!workspaceId && (projects.isLoading || sources.isLoading))
    || (!!projectId && bindings.isLoading)

  return (
    <PageContainer
      eyebrow="Workspace · Sources"
      title="Source"
      description="在 Workspace 维护可复用数据入口，并将固定版本绑定到具体 Project。"
      tabs={<RouteTabs tabs={AUTOMATION_TABS} />}
      actions={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Select
            value={workspaceId ?? ''}
            onValueChange={(value) => {
              setWorkspaceId(value || null)
              setProjectId(null)
            }}
          >
            <SelectTrigger className="min-w-48" aria-label="选择 Workspace">
              <Building2 className="size-3.5 text-muted-foreground" aria-hidden />
              <SelectValue>{selectedWorkspace?.name ?? '选择 Workspace'}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {(workspaces.data ?? []).map((workspace) => (
                <SelectItem key={workspace.id} value={workspace.id}>{workspace.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={projectId ?? ''} onValueChange={(value) => setProjectId(value || null)}>
            <SelectTrigger className="min-w-48" aria-label="选择 Project" disabled={!projects.data?.length}>
              <FolderKanban className="size-3.5 text-muted-foreground" aria-hidden />
              <SelectValue>{selectedProject?.name ?? '选择 Project'}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {(projects.data ?? []).map((project) => (
                <SelectItem key={project.id} value={project.id}>{project.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      }
    >
      {isLoading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error.message} hint={BACKEND_HINT} />
      ) : !workspaceId ? (
        <EmptyState title="暂无 Workspace" description="创建 Workspace 后即可维护可复用 Source。" />
      ) : (
        <div className="space-y-6">
          <section className="space-y-3" aria-labelledby="workspace-sources-title">
            <div>
              <h2 id="workspace-sources-title" className="text-sm font-semibold">Workspace Sources</h2>
              <p className="text-xs text-muted-foreground">这些 Source 可被当前 Workspace 下的多个 Project 复用。</p>
            </div>
            {!sources.data?.length ? (
              <EmptyState title="暂无 Source" description="当前 Workspace 还没有可复用数据入口。" />
            ) : (
              <Card className="overflow-hidden py-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>名称</TableHead>
                      <TableHead>Adapter</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead>当前 Revision</TableHead>
                      <TableHead>更新时间</TableHead>
                      <TableHead className="text-right">Project 绑定</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sources.data.map((source) => {
                      const isBound = boundSourceIds.has(source.id)
                      return (
                        <TableRow key={source.id}>
                          <TableCell>
                            <div className="font-medium">{source.name}</div>
                            <div className="font-mono text-2xs text-muted-foreground">{source.slug}</div>
                          </TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">{source.adapter_type}</TableCell>
                          <TableCell><SourceStatusBadge status={source.status} /></TableCell>
                          <TableCell className="font-mono">r{source.current_revision_number}</TableCell>
                          <TableCell className="text-muted-foreground">{formatRelative(source.updated_at)}</TableCell>
                          <TableCell className="text-right">
                            <Button
                              size="sm"
                              variant={isBound ? 'ghost' : 'outline'}
                              className="h-7 gap-1"
                              disabled={!projectId || source.status !== 'active' || isBound || createBinding.isPending}
                              onClick={() => void bindSource(source)}
                            >
                              <Link2 className="size-3.5" aria-hidden />
                              {isBound ? '已绑定' : '绑定当前 Revision'}
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </Card>
            )}
          </section>

          <section className="space-y-3" aria-labelledby="project-bindings-title">
            <div>
              <h2 id="project-bindings-title" className="text-sm font-semibold">Project SourceBindings</h2>
              <p className="text-xs text-muted-foreground">
                {selectedProject ? `${selectedProject.name} 当前的 Source 绑定记录。` : '选择 Project 查看绑定。'}
              </p>
            </div>
            {!projectId ? (
              <EmptyState title="暂无 Project" description="当前 Workspace 还没有可用于绑定 Source 的 Project。" />
            ) : !bindings.data?.length ? (
              <EmptyState title="暂无 SourceBinding" description="从上方选择一个活跃 Source 绑定其当前 Revision。" />
            ) : (
              <Card className="overflow-hidden py-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>绑定名称</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead>Binding Revision</TableHead>
                      <TableHead>更新时间</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {bindings.data.map((binding) => (
                      <TableRow key={binding.id}>
                        <TableCell>
                          <div className="font-medium">{binding.name}</div>
                          <div className="font-mono text-2xs text-muted-foreground">{binding.slug}</div>
                        </TableCell>
                        <TableCell>{sourceById.get(binding.source_id)?.name ?? binding.source_id}</TableCell>
                        <TableCell><SourceStatusBadge status={binding.status} /></TableCell>
                        <TableCell className="font-mono">r{binding.current_revision_number}</TableCell>
                        <TableCell className="text-muted-foreground">{formatRelative(binding.updated_at)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            )}
          </section>
        </div>
      )}
    </PageContainer>
  )
}
