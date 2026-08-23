'use client'

import { useState } from 'react'
import { GitBranch, Loader2, Play, Trash2, Workflow } from 'lucide-react'
import { toast } from 'sonner'

import { useDeletePlan, usePlans, useRunPlan } from '@/lib/api/hooks'
import type { PlanRead, PlanRunRead } from '@/lib/api/types'
import { formatRelative } from '@/lib/format'
import { PlanFormDialog } from '@/components/plans/plan-form-dialog'
import { PlanHealthBadge } from '@/components/plans/plan-health-badge'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

function runSummary(result: PlanRunRead): string {
  const failedSources = result.source_results.filter((segment) => !segment.success).length
  const base = `${result.success ? '成功' : '失败'} · 采集 ${result.collected} · 入库 ${result.stored} · 跳过 ${result.skipped}`
  if (result.error) return `${base} · ${result.error}`
  if (failedSources > 0) return `${base} · ${failedSources} 个来源失败`
  return base
}

export function PlanListPanel() {
  const { data, isLoading, isError, error } = usePlans({ limit: 100 })
  const plans = data?.data ?? []
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [runResults, setRunResults] = useState<Record<string, PlanRunRead>>({})
  const deleteMutation = useDeletePlan()
  const runMutation = useRunPlan()

  const handleDelete = (plan: PlanRead) => {
    if (confirmDeleteId !== plan.id) {
      setConfirmDeleteId(plan.id)
      return
    }
    deleteMutation.mutate(plan.id, {
      onSuccess: () => {
        toast.success('计划已删除')
        setConfirmDeleteId(null)
      },
      onError: (cause: Error) => toast.error(cause.message),
    })
  }

  const handleRun = (plan: PlanRead) => {
    runMutation.mutate(
      { id: plan.id },
      {
        onSuccess: (result) => {
          setRunResults((current) => ({ ...current, [plan.id]: result }))
          if (result.success) toast.success('运行完成')
          else toast.error(result.error ? `运行失败：${result.error}` : '运行失败')
        },
        onError: (cause: Error) => toast.error(cause.message),
      },
    )
  }

  if (isLoading) return <LoadingState />
  if (isError) return <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">计划</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Collection Canvas 图（Plan IR）的持久化记录。可视化编辑器尚未上线，这里管理名称、手动运行与健康状况。
          </p>
        </div>
        <PlanFormDialog />
      </div>

      {plans.length === 0 ? (
        <EmptyState title="暂无计划" description="创建一个计划后，可在此运行并查看健康状况。" />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {plans.map((plan) => {
            const running = runMutation.isPending && runMutation.variables?.id === plan.id
            const runResult = runResults[plan.id]
            const nodeCount = plan.graph?.nodes?.length ?? 0
            const edgeCount = plan.graph?.edges?.length ?? 0

            return (
              <Card key={plan.id}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-primary">
                        <Workflow className="size-4" />
                      </span>
                      <div className="min-w-0">
                        <CardTitle className="truncate text-sm">{plan.name}</CardTitle>
                        <p className="mt-1 truncate text-xs text-muted-foreground">
                          v{plan.version} · 更新于 {formatRelative(plan.updated_at)}
                        </p>
                      </div>
                    </div>
                    <PlanHealthBadge planId={plan.id} />
                  </div>
                </CardHeader>

                <CardContent className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={plan.runnable ? 'enabled' : 'disabled'} />
                    {plan.draft ? <Badge variant="outline">草稿</Badge> : null}
                    <Badge variant="secondary" className="gap-1">
                      <GitBranch className="size-3" />
                      {nodeCount} 节点 · {edgeCount} 连接
                    </Badge>
                  </div>

                  {runResult ? (
                    <p className={runResult.success ? 'text-xs text-success' : 'text-xs text-destructive'}>
                      {runSummary(runResult)}
                    </p>
                  ) : null}

                  <div className="flex flex-wrap items-center gap-1.5">
                    <Button
                      size="xs"
                      variant="outline"
                      disabled={!plan.runnable || running}
                      title={plan.runnable ? undefined : '计划暂不可运行：没有已落地（非草稿）的数据源节点'}
                      onClick={() => handleRun(plan)}
                      className="gap-1"
                    >
                      {running ? <Loader2 className="size-3 animate-spin" /> : <Play className="size-3" />}
                      运行
                    </Button>
                    <PlanFormDialog plan={plan} />
                    <Button
                      size="xs"
                      variant={confirmDeleteId === plan.id ? 'destructive' : 'ghost'}
                      disabled={deleteMutation.isPending}
                      onClick={() => handleDelete(plan)}
                      className="gap-1"
                    >
                      <Trash2 className="size-3" />
                      {confirmDeleteId === plan.id ? '确认删除' : '删除'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
