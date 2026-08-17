'use client'

import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { useDeleteSchedule, useSchedules, useSources } from '@/lib/api/hooks'
import type { CronSchedule } from '@/lib/api/types'
import { formatDateTime, formatRelative } from '@/lib/format'
import { ScheduleFormDialog } from '@/components/schedules/schedule-form-dialog'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export function ScheduleListPanel() {
  const { data, isLoading, isError, error } = useSchedules()
  const schedules = data?.data ?? []
  // Read-only join for display only — Source CRUD itself belongs to a
  // different resource owner; this only maps source_id -> name in this
  // panel's own table and picker.
  const sourcesQuery = useSources({ limit: 100 })
  const sourceNames = new Map((sourcesQuery.data?.data ?? []).map((source) => [source.id, source.name]))
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const deleteMutation = useDeleteSchedule()

  const handleDelete = (schedule: CronSchedule) => {
    if (confirmDeleteId !== schedule.id) {
      setConfirmDeleteId(schedule.id)
      return
    }
    deleteMutation.mutate(schedule.id, {
      onSuccess: () => {
        toast.success('调度已删除')
        setConfirmDeleteId(null)
      },
      onError: (cause: Error) => toast.error(cause.message),
    })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">调度</h2>
          <p className="mt-1 text-sm text-muted-foreground">管理自动化链路的定时触发计划。</p>
        </div>
        <ScheduleFormDialog />
      </div>

      {isLoading ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
      ) : schedules.length === 0 ? (
        <EmptyState title="暂无调度" description="创建 Cron 计划以定时触发采集任务。" />
      ) : (
        <Card className="overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>来源</TableHead>
                <TableHead>Cron 表达式</TableHead>
                <TableHead>类型</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>上次运行</TableHead>
                <TableHead>下次运行</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {schedules.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{s.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {sourceNames.get(s.source_id) ?? s.source_id}
                  </TableCell>
                  <TableCell>
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                      {s.cron_expression}
                    </code>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{s.is_one_time ? '一次性' : '周期'}</Badge>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={s.enabled ? 'enabled' : 'disabled'} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatRelative(s.last_run_at)}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDateTime(s.next_run_at)}</TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1.5">
                      <ScheduleFormDialog schedule={s} />
                      <Button
                        size="xs"
                        variant={confirmDeleteId === s.id ? 'destructive' : 'ghost'}
                        disabled={deleteMutation.isPending}
                        onClick={() => handleDelete(s)}
                        className="gap-1"
                      >
                        <Trash2 className="size-3" />
                        {confirmDeleteId === s.id ? '确认删除' : '删除'}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
