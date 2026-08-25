'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, Loader2, RotateCcw, Save } from 'lucide-react'
import { toast } from 'sonner'

import { useResetWorkspaceSettings, useUpdateWorkspaceSettings, useWorkspaceSettings } from '@/lib/api/hooks'
import type { WorkspaceSettingsRead, WorkspaceSettingsValues } from '@/lib/api/types'
import { BACKEND_HINT, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

const THEME_OPTIONS = [
  { value: 'system', label: '跟随系统' },
  { value: 'dark', label: '深色' },
  { value: 'light', label: '浅色' },
] as const

const SIDEBAR_OPTIONS = [
  { value: 'expanded', label: '展开' },
  { value: 'icon', label: '仅图标' },
  { value: 'collapsed', label: '收起' },
] as const

const LANDING_OPTIONS = [
  { value: '/dashboard', label: '概览' },
  { value: '/canvas', label: '节点画布' },
  { value: '/inbox', label: '任务与通知' },
] as const

const RETENTION_OPTIONS = [7, 30, 90, 365] as const

/** Small provenance hint next to a field's label — "已自定义" when the value
 *  has been overridden from the system default, "下次运行生效" when this
 *  particular field only takes effect on the next scheduled run rather than
 *  immediately (both come from WorkspaceSettingsRead, not guessed client-side). */
function FieldMeta({ read, field }: { read: WorkspaceSettingsRead; field: keyof WorkspaceSettingsValues }) {
  const isOverride = read.sources[field] === 'override'
  const isNextRun = read.apply_modes[field] === 'next_run'
  if (!isOverride && !isNextRun) return null
  return (
    <span className="inline-flex items-center gap-1.5">
      {isOverride ? (
        <Badge variant="outline" className="h-4 px-1.5 text-[10px] font-normal">
          已自定义
        </Badge>
      ) : null}
      {isNextRun ? <span className="text-[10px] text-muted-foreground">下次运行生效</span> : null}
    </span>
  )
}

export default function SettingsPage() {
  const { data, isLoading, isError, error } = useWorkspaceSettings()
  const updateMutation = useUpdateWorkspaceSettings()
  const resetMutation = useResetWorkspaceSettings()
  const [form, setForm] = useState<WorkspaceSettingsValues | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)

  // Sync local form state whenever the server value changes — on first load,
  // and again after our own save/reset mutations invalidate the query. Safe
  // to re-run: refetchOnWindowFocus is off (components/providers.tsx), so
  // this doesn't clobber an in-progress edit from a background refetch.
  useEffect(() => {
    if (data?.values) setForm(data.values)
  }, [data?.values])

  const set = <K extends keyof WorkspaceSettingsValues>(key: K, value: WorkspaceSettingsValues[K]) => {
    setForm((current) => (current ? { ...current, [key]: value } : current))
  }

  const hasChanges = Boolean(
    form && data?.values && Object.keys(form).some((key) => {
      const k = key as keyof WorkspaceSettingsValues
      return form[k] !== data.values[k]
    }),
  )

  const handleSave = (event: React.FormEvent) => {
    event.preventDefault()
    if (!form || !data?.values) return
    const changed: Partial<WorkspaceSettingsValues> = {}
    for (const key of Object.keys(form) as (keyof WorkspaceSettingsValues)[]) {
      if (form[key] !== data.values[key]) {
        Object.assign(changed, { [key]: form[key] })
      }
    }
    if (Object.keys(changed).length === 0) return
    updateMutation.mutate(changed, {
      onSuccess: () => toast.success('设置已保存'),
      onError: (cause) => toast.error((cause as Error).message),
    })
  }

  const handleReset = () => {
    resetMutation.mutate(undefined, {
      onSuccess: () => {
        toast.success('已重置为默认设置')
        setConfirmReset(false)
      },
      onError: (cause) => toast.error((cause as Error).message),
    })
  }

  return (
    <PageContainer
      eyebrow="Workspace"
      title="工作区设置"
      description="配置外观、执行、数据保留与通知偏好；随时可重置为默认值。"
    >
      {isLoading ? (
        <LoadingState />
      ) : isError || !data ? (
        <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
      ) : !form ? (
        <LoadingState />
      ) : (
        <form onSubmit={handleSave} className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="secondary">第 {data.revision} 版</Badge>
            <span>
              {data.updated_at ? `最近更新于 ${new Date(data.updated_at).toLocaleString()}` : '尚未自定义过设置'}
            </span>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">外观与导航</CardTitle>
              <CardDescription>控制台的显示方式和登录后默认落地页。</CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup className="gap-5">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field>
                    <FieldLabel htmlFor="settings-theme">
                      主题
                      <FieldMeta read={data} field="theme" />
                    </FieldLabel>
                    <Select value={form.theme} onValueChange={(value) => set('theme', value as WorkspaceSettingsValues['theme'])}>
                      <SelectTrigger id="settings-theme" className="w-full">
                        <SelectValue>
                          {(value: WorkspaceSettingsValues['theme'] | null) =>
                            value ? (THEME_OPTIONS.find((option) => option.value === value)?.label ?? value) : '选择主题'
                          }
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {THEME_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="settings-sidebar-mode">
                      侧边栏
                      <FieldMeta read={data} field="sidebar_mode" />
                    </FieldLabel>
                    <Select
                      value={form.sidebar_mode}
                      onValueChange={(value) => set('sidebar_mode', value as WorkspaceSettingsValues['sidebar_mode'])}
                    >
                      <SelectTrigger id="settings-sidebar-mode" className="w-full">
                        <SelectValue>
                          {(value: WorkspaceSettingsValues['sidebar_mode'] | null) =>
                            value ? (SIDEBAR_OPTIONS.find((option) => option.value === value)?.label ?? value) : '选择侧边栏'
                          }
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {SIDEBAR_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <Field>
                    <FieldLabel htmlFor="settings-landing-page">
                      默认落地页
                      <FieldMeta read={data} field="landing_page" />
                    </FieldLabel>
                    <Select
                      value={form.landing_page}
                      onValueChange={(value) => set('landing_page', value as WorkspaceSettingsValues['landing_page'])}
                    >
                      <SelectTrigger id="settings-landing-page" className="w-full">
                        <SelectValue>
                          {(value: WorkspaceSettingsValues['landing_page'] | null) =>
                            value ? (LANDING_OPTIONS.find((option) => option.value === value)?.label ?? value) : '选择默认落地页'
                          }
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {LANDING_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="settings-timezone">
                      时区
                      <FieldMeta read={data} field="timezone" />
                    </FieldLabel>
                    <Input
                      id="settings-timezone"
                      value={form.timezone}
                      onChange={(event) => set('timezone', event.target.value)}
                      placeholder="例如 Asia/Shanghai"
                    />
                  </Field>
                </div>

                <Field orientation="horizontal" className="items-center justify-between">
                  <FieldLabel htmlFor="settings-motion-enabled">
                    启用界面动效
                    <FieldMeta read={data} field="motion_enabled" />
                  </FieldLabel>
                  <Switch
                    id="settings-motion-enabled"
                    checked={form.motion_enabled}
                    onCheckedChange={(value) => set('motion_enabled', value)}
                  />
                </Field>
              </FieldGroup>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">执行</CardTitle>
              <CardDescription>调度和工作流运行时的默认行为。</CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup className="gap-5">
                <Field>
                  <FieldLabel htmlFor="settings-default-concurrency">
                    默认并发数
                    <FieldMeta read={data} field="default_concurrency" />
                  </FieldLabel>
                  <Input
                    id="settings-default-concurrency"
                    type="number"
                    min={1}
                    value={form.default_concurrency}
                    onChange={(event) => {
                      const next = Number(event.target.value)
                      set('default_concurrency', Number.isFinite(next) ? next : form.default_concurrency)
                    }}
                  />
                  <FieldDescription>新建调度未单独指定并发数时使用的默认值。</FieldDescription>
                </Field>

                <Field orientation="horizontal" className="items-center justify-between">
                  <FieldLabel htmlFor="settings-automatic-retries">
                    失败自动重试
                    <FieldMeta read={data} field="automatic_retries" />
                  </FieldLabel>
                  <Switch
                    id="settings-automatic-retries"
                    checked={form.automatic_retries}
                    onCheckedChange={(value) => set('automatic_retries', value)}
                  />
                </Field>
              </FieldGroup>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">数据保留</CardTitle>
              <CardDescription>采集到的原始数据在系统中保存多久。</CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup className="gap-5">
                <Field orientation="horizontal" className="items-center justify-between">
                  <FieldLabel htmlFor="settings-retain-raw-data">
                    保留原始数据
                    <FieldMeta read={data} field="retain_raw_data" />
                  </FieldLabel>
                  <Switch
                    id="settings-retain-raw-data"
                    checked={form.retain_raw_data}
                    onCheckedChange={(value) => set('retain_raw_data', value)}
                  />
                </Field>

                <Field>
                  <FieldLabel htmlFor="settings-retention-days">
                    保留天数
                    <FieldMeta read={data} field="retention_days" />
                  </FieldLabel>
                  <Select
                    value={String(form.retention_days)}
                    onValueChange={(value) =>
                      set('retention_days', Number(value) as WorkspaceSettingsValues['retention_days'])
                    }
                    disabled={!form.retain_raw_data}
                  >
                    <SelectTrigger id="settings-retention-days" className="w-full">
                      <SelectValue>
                        {(value: string | null) => (value ? `${value} 天` : '选择保留天数')}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {RETENTION_OPTIONS.map((days) => (
                        <SelectItem key={days} value={String(days)}>
                          {days} 天
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FieldDescription>
                    {form.retain_raw_data ? '超过此天数的原始数据将被清理。' : '关闭保留后，此项不生效。'}
                  </FieldDescription>
                </Field>
              </FieldGroup>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">通知</CardTitle>
              <CardDescription>选择哪些事件需要提醒。</CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup className="gap-4">
                <Field orientation="horizontal" className="items-center justify-between">
                  <FieldLabel htmlFor="settings-inbox-alerts">
                    收件箱提醒
                    <FieldMeta read={data} field="inbox_alerts" />
                  </FieldLabel>
                  <Switch
                    id="settings-inbox-alerts"
                    checked={form.inbox_alerts}
                    onCheckedChange={(value) => set('inbox_alerts', value)}
                  />
                </Field>
                <Field orientation="horizontal" className="items-center justify-between">
                  <FieldLabel htmlFor="settings-failure-alerts">
                    失败提醒
                    <FieldMeta read={data} field="failure_alerts" />
                  </FieldLabel>
                  <Switch
                    id="settings-failure-alerts"
                    checked={form.failure_alerts}
                    onCheckedChange={(value) => set('failure_alerts', value)}
                  />
                </Field>
                <Field orientation="horizontal" className="items-center justify-between">
                  <FieldLabel htmlFor="settings-agent-alerts">
                    Agent 提醒
                    <FieldMeta read={data} field="agent_alerts" />
                  </FieldLabel>
                  <Switch
                    id="settings-agent-alerts"
                    checked={form.agent_alerts}
                    onCheckedChange={(value) => set('agent_alerts', value)}
                  />
                </Field>
              </FieldGroup>
            </CardContent>
          </Card>

          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirmReset(true)}
              disabled={resetMutation.isPending}
              className="gap-1.5"
            >
              <RotateCcw className="size-4" />
              重置为默认值
            </Button>
            <Button type="submit" disabled={!hasChanges || updateMutation.isPending} className="gap-1.5">
              {updateMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
              {updateMutation.isPending ? '保存中…' : '保存更改'}
            </Button>
          </div>
        </form>
      )}

      <Dialog open={confirmReset} onOpenChange={setConfirmReset}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="size-4 text-destructive" aria-hidden />
              确认重置为默认值
            </DialogTitle>
            <DialogDescription>
              这会清除所有已自定义的工作区设置，恢复为系统默认值。此操作无法撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmReset(false)} disabled={resetMutation.isPending}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleReset} disabled={resetMutation.isPending}>
              {resetMutation.isPending ? '正在重置…' : '确认重置'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  )
}
