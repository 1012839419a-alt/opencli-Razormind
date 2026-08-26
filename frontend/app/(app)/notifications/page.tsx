'use client'

import { Fragment, useMemo, useState } from 'react'
import { Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  useDeleteNotificationRule,
  useInfiniteNotificationLogs,
  useInfiniteNotificationRules,
  useNotificationRulesByIds,
} from '@/lib/api/hooks'
import type { NotificationLog, NotificationRule } from '@/lib/api/types'
import { formatDateTime, formatRelative } from '@/lib/format'
import { notificationChannelLabel } from '@/lib/notification-channels'
import {
  acknowledgementStatusPresentation,
  dedupeDeliveryAttempts,
  sanitizedDeliveryErrorSummary,
  transportStatusPresentation,
  type DeliveryStatusPresentation,
} from '@/lib/notifications/delivery-status'
import { cn } from '@/lib/utils'
import { NotificationRuleFormDialog } from '@/components/notifications/notification-rule-form-dialog'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { ACTION_CENTER_TABS, RouteTabs } from '@/components/shell/route-tabs'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const DELIVERY_PAGE_SIZE = 25
const RULE_PAGE_SIZE = 50

function DeliveryStatusBadge({ presentation }: { presentation: DeliveryStatusPresentation }) {
  return (
    <Badge
      variant={presentation.tone === 'negative' ? 'destructive' : 'outline'}
      className={cn(
        presentation.tone === 'positive' &&
          'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
        presentation.tone === 'warning' &&
          'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
        presentation.tone === 'informative' &&
          'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300',
        presentation.tone === 'neutral' && 'text-muted-foreground',
      )}
      title={presentation.description}
    >
      {presentation.label}
    </Badge>
  )
}

function RuleTable({ rules }: { rules: NotificationRule[] }) {
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
        {rules.map((rule) => (
          <Fragment key={rule.id}>
            <TableRow>
              <TableCell className="font-medium">{rule.name}</TableCell>
              <TableCell>
                <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                  {rule.trigger_event}
                </code>
              </TableCell>
              <TableCell>
                <Badge variant="secondary">{notificationChannelLabel(rule.notifier_type)}</Badge>
              </TableCell>
              <TableCell>
                <StatusBadge status={rule.enabled ? 'enabled' : 'disabled'} />
              </TableCell>
              <TableCell>
                <div className="flex items-center justify-end gap-1">
                  <NotificationRuleFormDialog
                    mode="edit"
                    rule={rule}
                    triggerLabel=""
                    triggerIcon={<Pencil className="size-3.5" />}
                    triggerVariant="ghost"
                    triggerSize="icon-sm"
                    triggerAriaLabel="编辑规则"
                  />
                  <Button
                    variant={confirmDeleteId === rule.id ? 'destructive' : 'ghost'}
                    size="icon-sm"
                    aria-label={confirmDeleteId === rule.id ? '确认删除并清除投递证据' : '删除规则'}
                    disabled={deleteMutation.isPending}
                    onClick={() => handleDelete(rule)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
            {confirmDeleteId === rule.id ? (
              <TableRow className="bg-destructive/5">
                <TableCell colSpan={5}>
                  <p className="text-sm text-destructive" role="alert">
                    再次点击删除将永久删除该规则及其全部投递证据，此操作不可恢复。
                  </p>
                </TableCell>
              </TableRow>
            ) : null}
          </Fragment>
        ))}
      </TableBody>
    </Table>
  )
}

function DeliveryEvidenceTable({
  logs,
  rulesById,
}: {
  logs: NotificationLog[]
  rulesById: Map<string, NotificationRule>
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>通知规则</TableHead>
          <TableHead>技术提交</TableHead>
          <TableHead>业务回执</TableHead>
          <TableHead>关联记录</TableHead>
          <TableHead>发生时间</TableHead>
          <TableHead className="max-w-64">错误摘要</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {logs.map((log) => {
          const rule = rulesById.get(log.rule_id)
          const errorSummary =
            sanitizedDeliveryErrorSummary(log.error_message) ||
            (log.ack_status === 'failed' ? '业务回执失败' : null)
          return (
            <TableRow key={log.id}>
              <TableCell>
                <div className="font-medium">{rule?.name ?? `规则 ${log.rule_id.slice(0, 8)}`}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {rule ? notificationChannelLabel(rule.notifier_type) : log.rule_id.slice(0, 8)}
                </div>
              </TableCell>
              <TableCell>
                <DeliveryStatusBadge presentation={transportStatusPresentation(log.status)} />
              </TableCell>
              <TableCell>
                <div className="flex flex-col items-start gap-1">
                  <DeliveryStatusBadge
                    presentation={acknowledgementStatusPresentation(log.ack_status, log.status)}
                  />
                  {log.acked_at ? (
                    <span
                      className="text-xs text-muted-foreground"
                      title={formatDateTime(log.acked_at)}
                    >
                      {formatRelative(log.acked_at)}
                    </span>
                  ) : null}
                </div>
              </TableCell>
              <TableCell>
                {log.record_id ? (
                  <code className="font-mono text-xs" title={log.record_id}>
                    {log.record_id.slice(0, 8)}
                  </code>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell className="text-muted-foreground" title={formatDateTime(log.created_at)}>
                {formatRelative(log.created_at)}
              </TableCell>
              <TableCell className="max-w-64">
                {errorSummary ? (
                  <span className="line-clamp-2 text-sm text-destructive" title={errorSummary}>
                    {errorSummary}
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

export default function NotificationsPage() {
  const rulesQuery = useInfiniteNotificationRules({ limit: RULE_PAGE_SIZE })
  const logsQuery = useInfiniteNotificationLogs({ limit: DELIVERY_PAGE_SIZE })
  const rules = useMemo(
    () => dedupeDeliveryAttempts(rulesQuery.data?.pages.flatMap((page) => page.data) ?? []),
    [rulesQuery.data],
  )
  const logs = useMemo(
    () => dedupeDeliveryAttempts(logsQuery.data?.pages.flatMap((page) => page.data) ?? []),
    [logsQuery.data],
  )
  const loadedRulesById = useMemo(() => new Map(rules.map((rule) => [rule.id, rule])), [rules])
  const missingRuleIds = useMemo(
    () => [...new Set(logs.map((log) => log.rule_id))].filter((id) => !loadedRulesById.has(id)),
    [loadedRulesById, logs],
  )
  const ruleLookups = useNotificationRulesByIds(missingRuleIds)
  const rulesById = new Map(loadedRulesById)
  ruleLookups.forEach((query) => {
    if (query.data) rulesById.set(query.data.id, query.data)
  })
  const totalRules = Math.max(rulesQuery.data?.pages[0]?.meta?.total ?? 0, rules.length)
  const totalLogs = Math.max(logsQuery.data?.pages[0]?.meta?.total ?? 0, logs.length)

  return (
    <PageContainer
      eyebrow="Delivery rules"
      title="任务与通知"
      description="管理通知规则，并核对从通道提交到业务回执的完整投递证据。"
      tabs={<RouteTabs tabs={ACTION_CENTER_TABS} />}
      actions={
        <NotificationRuleFormDialog
          mode="create"
          triggerLabel="创建规则"
          triggerIcon={<Plus className="size-4" />}
        />
      }
    >
      <section aria-labelledby="notification-rules-title" className="space-y-3">
        <div>
          <h2 id="notification-rules-title" className="text-lg font-semibold">
            通知规则
          </h2>
          <p className="text-sm text-muted-foreground">配置采集事件触发的通知方式。</p>
        </div>
        {rulesQuery.isLoading && rules.length === 0 ? (
          <LoadingState />
        ) : rulesQuery.isError && rules.length === 0 ? (
          <ErrorState
            message={(rulesQuery.error as Error)?.message}
            hint={BACKEND_HINT}
            action={
              <Button variant="outline" onClick={() => rulesQuery.refetch()}>
                重试
              </Button>
            }
          />
        ) : rules.length === 0 ? (
          <EmptyState title="暂无通知规则" description="创建规则以在采集事件发生时收到通知。" />
        ) : (
          <Card className="overflow-hidden py-0">
            <div className="overflow-x-auto">
              <RuleTable rules={rules} />
            </div>
            <CardFooter className="flex-col items-stretch gap-3">
              {rulesQuery.isError ? (
                <div
                  className="flex flex-wrap items-center justify-between gap-2 text-sm text-destructive"
                  role="alert"
                >
                  <span>更新规则列表失败，已加载的规则仍保留。</span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      rulesQuery.isFetchNextPageError
                        ? rulesQuery.fetchNextPage()
                        : rulesQuery.refetch()
                    }
                  >
                    重试
                  </Button>
                </div>
              ) : null}
              <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
                <span>已显示 {rules.length} / {totalRules} 条规则</span>
                {rulesQuery.hasNextPage ? (
                  <Button
                    variant="outline"
                    onClick={() => rulesQuery.fetchNextPage()}
                    disabled={rulesQuery.isFetchingNextPage}
                  >
                    {rulesQuery.isFetchingNextPage ? '正在加载…' : '加载更多规则'}
                  </Button>
                ) : null}
              </div>
            </CardFooter>
          </Card>
        )}
      </section>

      <section aria-labelledby="delivery-evidence-title">
        <Card>
          <CardHeader className="border-b">
            <div>
              <CardTitle id="delivery-evidence-title">投递证据</CardTitle>
              <CardDescription className="mt-1">
                技术提交与业务回执分开显示；仅展示脱敏状态、关联标识和错误摘要。
              </CardDescription>
            </div>
            <CardAction>
              <Button
                variant="outline"
                size="sm"
                onClick={() => logsQuery.refetch()}
                disabled={logsQuery.isFetching}
                aria-label="刷新投递证据"
              >
                <RefreshCw className={cn('size-4', logsQuery.isFetching && 'animate-spin')} />
                刷新
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-4">
            {logsQuery.isLoading && logs.length === 0 ? (
              <LoadingState rows={3} />
            ) : logsQuery.isError && logs.length === 0 ? (
              <ErrorState
                message={(logsQuery.error as Error)?.message}
                hint="通知规则仍可继续管理；恢复连接后可单独重试投递证据。"
                action={
                  <Button variant="outline" onClick={() => logsQuery.refetch()}>
                    重试
                  </Button>
                }
              />
            ) : logs.length === 0 ? (
              <EmptyState
                title="暂无投递证据"
                description="通知规则触发后，这里会显示提交和回执状态。"
              />
            ) : (
              <>
                {logsQuery.isError ? (
                  <div
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
                    role="alert"
                  >
                    <span>更新投递证据失败，已加载的记录仍保留。</span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        logsQuery.isFetchNextPageError
                          ? logsQuery.fetchNextPage()
                          : logsQuery.refetch()
                      }
                    >
                      重试
                    </Button>
                  </div>
                ) : null}
                <div className="overflow-x-auto rounded-lg border">
                  <DeliveryEvidenceTable logs={logs} rulesById={rulesById} />
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
                  <span>已显示 {logs.length} / {totalLogs} 条</span>
                  {logsQuery.hasNextPage ? (
                    <Button
                      variant="outline"
                      onClick={() => logsQuery.fetchNextPage()}
                      disabled={logsQuery.isFetchingNextPage}
                    >
                      {logsQuery.isFetchingNextPage
                        ? '正在加载…'
                        : logsQuery.isFetchNextPageError
                          ? '重试加载更多'
                          : '加载更多'}
                    </Button>
                  ) : null}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </section>
    </PageContainer>
  )
}
