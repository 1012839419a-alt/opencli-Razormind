'use client'

import { useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { useDeleteNotificationRule, useNotificationRules } from '@/lib/api/hooks'
import type { NotificationRule } from '@/lib/api/types'
import { notificationChannelLabel } from '@/lib/notification-channels'
import { NotificationRuleFormDialog } from '@/components/notifications/notification-rule-form-dialog'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { ACTION_CENTER_TABS, RouteTabs } from '@/components/shell/route-tabs'
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

export default function NotificationsPage() {
  const { data, isLoading, isError, error } = useNotificationRules()
  const rules = data?.data ?? []
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const deleteMutation = useDeleteNotificationRule()

  const handleDelete = (rule: NotificationRule) => {
    if (confirmDeleteId !== rule.id) {
      setConfirmDeleteId(rule.id)
      return
    }
    deleteMutation.mutate(rule.id, {
      onSuccess: () => {
        toast.success('已删除通知规则')
        setConfirmDeleteId(null)
      },
      onError: (error: Error) => toast.error(error.message),
    })
  }

  return (
    <PageContainer
      eyebrow="Delivery rules"
      title="任务与通知"
      description="管理采集事件触发的通知规则；投递失败会汇入待处理视图。"
      tabs={<RouteTabs tabs={ACTION_CENTER_TABS} />}
      actions={
        <NotificationRuleFormDialog
          mode="create"
          triggerLabel="创建规则"
          triggerIcon={<Plus className="size-4" />}
        />
      }
    >
      {isLoading ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
      ) : rules.length === 0 ? (
        <EmptyState title="暂无通知规则" description="创建规则以在采集事件发生时收到通知。" />
      ) : (
        <Card className="overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>触发事件</TableHead>
                <TableHead>通知方式</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-medium">{r.name}</TableCell>
                  <TableCell>
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                      {r.trigger_event}
                    </code>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {notificationChannelLabel(r.notifier_type)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={r.enabled ? 'enabled' : 'disabled'} />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1">
                      <NotificationRuleFormDialog
                        mode="edit"
                        rule={r}
                        triggerLabel=""
                        triggerIcon={<Pencil className="size-3.5" />}
                        triggerVariant="ghost"
                        triggerSize="icon-sm"
                        triggerAriaLabel="编辑规则"
                      />
                      <Button
                        variant={confirmDeleteId === r.id ? 'destructive' : 'ghost'}
                        size="icon-sm"
                        aria-label={confirmDeleteId === r.id ? '确认删除' : '删除规则'}
                        disabled={deleteMutation.isPending}
                        onClick={() => handleDelete(r)}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </PageContainer>
  )
}
