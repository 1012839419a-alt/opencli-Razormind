'use client'

import { useEffect, useState } from 'react'
import { ChevronDown } from 'lucide-react'

import { BrowserSpacesPanel } from '@/features/browser-spaces/browser-spaces-panel'
import { useMyWorkspaces } from '@/lib/api/hooks'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'

export default function BrowsersPage() {
  const workspaces = useMyWorkspaces()
  const [workspaceId, setWorkspaceId] = useState<string | null>(null)

  useEffect(() => {
    if (!workspaceId && workspaces.data?.length) setWorkspaceId(workspaces.data[0].id)
  }, [workspaceId, workspaces.data])

  if (workspaces.isLoading) return <PageContainer title="Browser Spaces" description="为 Agent 保留受控浏览器执行边界。"><LoadingState rows={4} /></PageContainer>
  if (workspaces.isError) return <PageContainer title="Browser Spaces"><ErrorState message={(workspaces.error as Error)?.message} hint={BACKEND_HINT} /></PageContainer>
  if (!workspaces.data?.length) return <PageContainer title="Browser Spaces"><EmptyState title="尚未加入 Workspace" description="加入 Workspace 后才能创建 Agent 的浏览器 Space。" /></PageContainer>

  return <PageContainer eyebrow="Browser Operator" title="Browser Spaces" description="为 Agent 分配一个既有浏览器实例，并以可取消的任务租约运行受限 capability。" actions={<label className="relative"><select value={workspaceId ?? ''} onChange={(event) => setWorkspaceId(event.target.value)} className="h-9 appearance-none rounded-lg border bg-background py-1 pl-3 pr-8 text-sm" aria-label="选择 Workspace">{workspaces.data.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}</select><ChevronDown className="pointer-events-none absolute right-2.5 top-2.5 size-4 text-muted-foreground" /></label>}>
    {workspaceId ? <BrowserSpacesPanel workspaceId={workspaceId} /> : null}
  </PageContainer>
}
