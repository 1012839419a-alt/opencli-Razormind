'use client'

import Link from 'next/link'
import { useState } from 'react'
import { ArrowUpRight, Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  useDeleteNotificationRule,
  useNotificationLogs,
  useNotificationRules,
} from '@/lib/api/hooks'
import type { NotificationRule } from '@/lib/api/types'
import { notificationChannelLabel } from '@/lib/notification-channels'
import { notificationTriggerLabel } from '@/lib/notification-events'
import { formatDateTime, formatRelative } from '@/lib/format'
import { NotificationRuleFormDialog } from '@/components/notifications/notification-rule-form-dialog'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { ACTION_CENTER_TABS, RouteTabs } from '@/components/shell/route-tabs'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

type NotificationView = 'rules' | 'logs'

function NotificationLogsPanel({ enabled, rules }: { enabled: boolean; rules: NotificationRule[] }) {
  const { data, isLoading, isError, error } = useNotificationLogs(
    { page: 1, limit: 100 },
    { enabled },
  )
  const logs = data?.data ?? []
  const ruleNames = new Map(rules.map((rule) => [rule.id, rule.name]))

  if (isLoading) return <LoadingState />
  if (isError) {
    return <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
  }
  if (logs.length === 0) {
    return (
      <EmptyState
        title="暂无投递记录"
        description="通知规则触发后，每次投递都会在这里留下状态、回执和错误摘要。"
      />
    )
  }

  return (
    <Card className="overflow-hidden py-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>时间</TableHead>
            <TableHead>规则</TableHead>
            <TableHead>投递状态</TableHead>
            <TableHead>业务回执</TableHead>
            <TableHead>记录</TableHead>
            <TableHead>错误摘要</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {logs.map((log) => (
            <TableRow key={log.id}>
              <TableCell className="whitespace-nowrap">
                <div>{formatRelative(log.created_at)}</div>
                <div className="mt-1 text-2xs text-muted-foreground">
                  {formatDateTime(log.created_at)}
                </div>
              </TableCell>
              <TableCell>
                <div className="font-medium">{ruleNames.get(log.rule_id) ?? '规则已删除'}</div>
                <code className="mt-1 block font-mono text-2xs text-muted-foreground">
                  {log.rule_id.slice(0, 8)}
                </code>
              </TableCell>
              <TableCell>
                <StatusBadge status={log.status} />
              </TableCell>
              <TableCell>
                <StatusBadge status={log.ack_status} />
              </TableCell>
              <TableCell>
                {log.record_id ? (
                  <Link
                    href="/records"
                    className="inline-flex items-center gap-1 font-mono text-xs hover:underline"
                    title="打开成果与数据"
                  >
                    {log.record_id.slice(0, 8)}
                    <ArrowUpRight className="size-3.5 text-muted-foreground" />
                  </Link>
                ) : (
                  <span className="text-muted-foreground">任务事件</span>
                )}
              </TableCell>
              <TableCell className="max-w-sm">
                <span className="block truncate text-muted-foreground" title={log.error_message ?? undefined}>
                  {log.error_message ?? '—'}
                </span>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  )
}

export default function NotificationsPage() {
  const { data, isLoading, isError, error } = useNotificationRules()
  const rules = data?.data ?? []
  const [view, setView] = useState<NotificationView>('rules')
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
      <Tabs
        value={view}
        onValueChange={(value) => setView(String(value) as NotificationView)}
        className="gap-4"
      >
        <TabsList variant="line">
          <TabsTrigger value="rules">通知规则</TabsTrigger>
          <TabsTrigger value="logs">
            投递记录
            <Badge variant="secondary" className="ml-1">
              真实状态
            </Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="rules" className="data-[hidden]:hidden">
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
                          {notificationTriggerLabel(r.trigger_event)}
                        </code>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{notificationChannelLabel(r.notifier_type)}</Badge>
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
        </TabsContent>

        <TabsContent value="logs" className="data-[hidden]:hidden">
          <NotificationLogsPanel enabled={view === 'logs'} rules={rules} />
        </TabsContent>
      </Tabs>
    </PageContainer>
  )
}
