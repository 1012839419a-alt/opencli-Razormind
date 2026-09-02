'use client'

import { useState } from 'react'
import { Bot, Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { useAgents, useDeleteAgent } from '@/lib/api/hooks'
import type { AIAgent } from '@/lib/api/types'
import { AgentFormDialog } from '@/components/agents/agent-form-dialog'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { AUTOMATION_TABS, RouteTabs } from '@/components/shell/route-tabs'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const PROCESSOR_LABEL: Record<string, string> = {
  claude: 'Claude',
  openai: 'OpenAI',
  local: '本地模型',
}

export default function AgentsPage() {
  const { data, isLoading, isError, error } = useAgents()
  const agents = data?.data ?? []
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const deleteMutation = useDeleteAgent()

  const handleDelete = (agent: AIAgent) => {
    if (confirmDeleteId !== agent.id) {
      setConfirmDeleteId(agent.id)
      return
    }
    deleteMutation.mutate(agent.id, {
      onSuccess: () => {
        toast.success('已删除 Agent')
        setConfirmDeleteId(null)
      },
      onError: (cause: Error) => toast.error(cause.message),
    })
  }

  return (
    <PageContainer
      eyebrow="Automation"
      title="自动化与 Agent"
      description="管理负责分析、判断和富化采集数据的 Agent。"
      tabs={<RouteTabs tabs={AUTOMATION_TABS} />}
      actions={
        <AgentFormDialog mode="create" triggerLabel="添加 Agent" triggerIcon={<Plus className="size-4" />} />
      }
    >
      {isLoading ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
      ) : agents.length === 0 ? (
        <EmptyState title="暂无智能体" description="创建 AI 智能体以处理采集到的数据。" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((a) => {
            const confirming = confirmDeleteId === a.id
            return (
              <Card key={a.id}>
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="flex size-8 items-center justify-center rounded-md bg-muted text-chart-3">
                        <Bot className="size-4" />
                      </span>
                      <CardTitle className="text-base">{a.name}</CardTitle>
                    </div>
                    <StatusBadge status={a.enabled ? 'enabled' : 'disabled'} />
                  </div>
                  {a.description ? (
                    <CardDescription className="line-clamp-2">{a.description}</CardDescription>
                  ) : null}
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">{PROCESSOR_LABEL[a.processor_type] ?? a.processor_type}</Badge>
                    {a.model ? <Badge variant="outline">{a.model}</Badge> : null}
                  </div>

                  {confirming ? (
                    <p className="text-xs text-destructive">
                      删除后，引用该 Agent 的调度和工作流会在下次运行时因找不到 Agent 而报错，请确认。
                    </p>
                  ) : null}

                  <div className="flex flex-wrap items-center gap-1.5">
                    <AgentFormDialog
                      mode="edit"
                      agent={a}
                      triggerLabel="编辑"
                      triggerIcon={<Pencil className="size-3" />}
                      triggerVariant="ghost"
                      triggerSize="xs"
                    />
                    <Button
                      size="xs"
                      variant={confirming ? 'destructive' : 'ghost'}
                      disabled={deleteMutation.isPending}
                      onClick={() => handleDelete(a)}
                      className="gap-1"
                    >
                      <Trash2 className="size-3" />
                      {confirming ? '确认删除' : '删除'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </PageContainer>
  )
}
