'use client'

import { useState, type FormEvent } from 'react'
import { Loader2, Pencil, Plus } from 'lucide-react'
import { toast } from 'sonner'

import { useAgents, useCreateSchedule, useSources, useUpdateSchedule } from '@/lib/api/hooks'
import type { CronSchedule } from '@/lib/api/types'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'

// Base UI's Select treats "" as "no value" — use a sentinel for the "don't
// assign an agent" choice so it round-trips through the Select cleanly, then
// map it back to `undefined` (omit agent_id) right before the mutation call.
const NO_AGENT = '__none__'

const CRON_PRESETS: { label: string; value: string }[] = [
  { label: '每 5 分钟', value: '*/5 * * * *' },
  { label: '每小时', value: '0 * * * *' },
  { label: '每天 09:00', value: '0 9 * * *' },
]

type ScheduleFormState = {
  source_id: string
  agent_id: string
  name: string
  cron_expression: string
  timezone: string
  parameters: string
  enabled: boolean
  is_one_time: boolean
}

function formState(schedule?: CronSchedule): ScheduleFormState {
  return {
    source_id: schedule?.source_id ?? '',
    agent_id: schedule?.agent_id ?? NO_AGENT,
    name: schedule?.name ?? '',
    cron_expression: schedule?.cron_expression ?? '',
    timezone: schedule?.timezone ?? 'Asia/Shanghai',
    parameters: JSON.stringify(schedule?.parameters ?? {}, null, 2),
    enabled: schedule?.enabled ?? true,
    is_one_time: schedule?.is_one_time ?? false,
  }
}

/** Create + edit dialog for a CronSchedule. `source_id` is create-only — the
 * backend's CronScheduleUpdate schema has no such field, so an existing
 * schedule shows its bound source as read-only text instead of a picker. */
export function ScheduleFormDialog({ schedule }: { schedule?: CronSchedule }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<ScheduleFormState>(() => formState(schedule))
  const sourcesQuery = useSources({ limit: 100 })
  const agentsQuery = useAgents()
  const sources = sourcesQuery.data?.data ?? []
  const agents = agentsQuery.data?.data ?? []
  const createMutation = useCreateSchedule()
  const updateMutation = useUpdateSchedule()
  const pending = createMutation.isPending || updateMutation.isPending
  const currentSourceName = schedule
    ? (sources.find((source) => source.id === schedule.source_id)?.name ?? schedule.source_id)
    : null

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (nextOpen) setForm(formState(schedule))
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!form.name.trim()) {
      toast.error('请填写调度名称')
      return
    }
    if (!form.cron_expression.trim()) {
      toast.error('请填写 Cron 表达式')
      return
    }
    if (!schedule && !form.source_id) {
      toast.error('请选择要触发的数据源')
      return
    }

    let parameters: Record<string, unknown>
    try {
      const parsed: unknown = form.parameters.trim() ? JSON.parse(form.parameters) : {}
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
        throw new Error('参数必须是 JSON 对象')
      }
      parameters = parsed as Record<string, unknown>
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '参数 JSON 无效')
      return
    }

    const options = {
      onSuccess: () => {
        toast.success(schedule ? '调度已更新' : '调度已创建')
        setOpen(false)
      },
      onError: (cause: Error) => toast.error(cause.message),
    }

    const common = {
      name: form.name.trim(),
      cron_expression: form.cron_expression.trim(),
      timezone: form.timezone.trim() || 'UTC',
      parameters,
      enabled: form.enabled,
      is_one_time: form.is_one_time,
      agent_id: form.agent_id === NO_AGENT ? undefined : form.agent_id,
    }

    if (schedule) {
      updateMutation.mutate({ id: schedule.id, data: common }, options)
      return
    }
    createMutation.mutate({ ...common, source_id: form.source_id }, options)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button size={schedule ? 'xs' : 'sm'} variant={schedule ? 'ghost' : 'default'} />}>
        {schedule ? <Pencil className="size-3" /> : <Plus className="size-4" />}
        {schedule ? '编辑' : '新建调度'}
      </DialogTrigger>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>{schedule ? '编辑调度' : '新建调度'}</DialogTitle>
            <DialogDescription>Cron 触发指定数据源按计划采集；来源一旦创建不可更改。</DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-2">
            <Label htmlFor="schedule-source">数据源</Label>
            {schedule ? (
              <div className="flex min-h-8 items-center rounded-lg border border-dashed bg-muted/15 px-3 text-sm text-muted-foreground">
                {currentSourceName}
              </div>
            ) : (
              <Select
                value={form.source_id || undefined}
                onValueChange={(value) => setForm((current) => ({ ...current, source_id: value as string }))}
              >
                <SelectTrigger id="schedule-source" className="w-full">
                  {/* Base UI's SelectValue shows the raw value string unless told
                      how to format it — it does not resolve a label from the
                      rendered SelectItem children on its own (see
                      node_modules/@base-ui/react's resolveValueLabel.mjs: it
                      only consults an `items` map/array, which isn't wired
                      here). The `children` render-prop is the documented way
                      to map id -> display label instead of a raw UUID. */}
                  <SelectValue>
                    {(value: string | null) =>
                      value
                        ? (sources.find((source) => source.id === value)?.name ?? value)
                        : sourcesQuery.isLoading
                          ? '正在读取数据源…'
                          : '选择数据源'
                    }
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {sources.map((source) => (
                    <SelectItem key={source.id} value={source.id}>
                      {source.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="schedule-name">名称</Label>
              <Input
                id="schedule-name"
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="schedule-timezone">时区</Label>
              <Input
                id="schedule-timezone"
                value={form.timezone}
                onChange={(event) => setForm((current) => ({ ...current, timezone: event.target.value }))}
                placeholder="Asia/Shanghai"
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="schedule-cron">Cron 表达式</Label>
            <Input
              id="schedule-cron"
              value={form.cron_expression}
              onChange={(event) => setForm((current) => ({ ...current, cron_expression: event.target.value }))}
              placeholder="0 9 * * *"
              className="font-mono"
              required
            />
            <div className="flex flex-wrap gap-1.5">
              {CRON_PRESETS.map((preset) => (
                <Button
                  key={preset.value}
                  type="button"
                  size="xs"
                  variant="outline"
                  onClick={() => setForm((current) => ({ ...current, cron_expression: preset.value }))}
                >
                  {preset.label}
                </Button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">5 位标准 Cron：分 时 日 月 周。</p>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="schedule-agent">处理 Agent（可选）</Label>
            <Select
              value={form.agent_id}
              onValueChange={(value) => setForm((current) => ({ ...current, agent_id: value as string }))}
            >
              <SelectTrigger id="schedule-agent" className="w-full">
                <SelectValue>
                  {(value: string | null) =>
                    !value || value === NO_AGENT
                      ? '不指定'
                      : (agents.find((agent) => agent.id === value)?.name ?? value)
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_AGENT}>不指定</SelectItem>
                {agents.map((agent) => (
                  <SelectItem key={agent.id} value={agent.id}>
                    {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="schedule-parameters">运行参数 JSON（可选）</Label>
            <Textarea
              id="schedule-parameters"
              value={form.parameters}
              onChange={(event) => setForm((current) => ({ ...current, parameters: event.target.value }))}
              className="min-h-20 font-mono text-xs"
            />
          </div>

          <div className="grid gap-3 rounded-lg border p-3 sm:grid-cols-2">
            <label className="flex items-center justify-between gap-3 text-sm">
              <span>启用调度</span>
              <Switch
                checked={form.enabled}
                onCheckedChange={(checked) => setForm((current) => ({ ...current, enabled: checked }))}
              />
            </label>
            <label className="flex items-center justify-between gap-3 text-sm">
              <span>仅执行一次</span>
              <Switch
                checked={form.is_one_time}
                onCheckedChange={(checked) => setForm((current) => ({ ...current, is_one_time: checked }))}
              />
            </label>
          </div>

          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending ? <Loader2 className="size-4 animate-spin" /> : null}
              {schedule ? '保存' : '创建'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
