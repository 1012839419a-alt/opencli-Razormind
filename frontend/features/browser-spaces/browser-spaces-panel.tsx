'use client'

import { useEffect, useState } from 'react'
import { CircleStop, Plus, RefreshCw, Send, ShieldCheck, X } from 'lucide-react'
import { toast } from 'sonner'

import { EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

import { useBrowserSpaceActions, useBrowserSpaceEvents, useBrowserSpaces } from './hooks'
import type { BrowserSpace, BrowserSpaceEvent, BrowserSpaceTask } from './types'

const TERMINAL_TASKS = new Set(['completed', 'failed', 'cancelled'])
const SENSITIVE_KEY = /authorization|cookie|credential|endpoint|profile|secret|token|password/i

function safeValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(safeValue)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, SENSITIVE_KEY.test(key) ? '[redacted]' : safeValue(item)]))
  }
  return value
}

function safeJson(value: unknown) {
  return JSON.stringify(safeValue(value), null, 2)
}

function errorCode(error: unknown) {
  const message = error instanceof Error ? error.message : '请求失败'
  if (message.includes('browser_instance_in_use')) return 'browser_instance_in_use：该浏览器实例已由另一个 Space 保留。'
  if (message.includes('space_task_in_progress')) return 'space_task_in_progress：该 Space 正在执行任务。'
  return message
}

function statusClass(status: string) {
  if (status === 'completed' || status === 'idle') return 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
  if (status === 'running' || status === 'queued') return 'bg-sky-500/10 text-sky-700 dark:text-sky-300'
  if (status === 'failed' || status === 'error') return 'bg-destructive/10 text-destructive'
  return 'bg-muted text-muted-foreground'
}

function newestTask(space: BrowserSpace): BrowserSpaceTask | null {
  return space.latest_task ?? null
}

function EventLog({ events }: { events: BrowserSpaceEvent[] }) {
  if (!events.length) return <p className="text-sm text-muted-foreground">尚无已持久化事件。</p>
  return (
    <ol className="space-y-3 border-l border-border pl-4">
      {events.map((event) => (
        <li key={event.id} className="relative text-sm">
          <span className="absolute -left-[21px] top-1.5 size-2 rounded-full bg-primary" />
          <div className="flex flex-wrap items-baseline gap-x-2"><span className="font-medium">#{event.sequence} {event.kind}</span><time className="text-xs text-muted-foreground">{new Date(event.created_at).toLocaleString()}</time></div>
          {event.payload ? <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-muted/60 p-2 text-xs text-muted-foreground">{safeJson(event.payload)}</pre> : null}
        </li>
      ))}
    </ol>
  )
}

function SpaceDetails({ workspaceId, space, onClose }: { workspaceId: string; space: BrowserSpace; onClose: () => void }) {
  const [capability, setCapability] = useState(space.granted_capabilities[0] ?? 'snapshot')
  const [argsText, setArgsText] = useState('{}')
  const [timeout, setTimeout] = useState('60')
  const events = useBrowserSpaceEvents(workspaceId, space.id)
  const actions = useBrowserSpaceActions()
  const task = newestTask(space)
  const taskActive = task && !TERMINAL_TASKS.has(task.status)

  useEffect(() => {
    if (!space.granted_capabilities.includes(capability)) setCapability(space.granted_capabilities[0] ?? '')
  }, [capability, space.granted_capabilities])

  async function submit() {
    if (!capability || !space.granted_capabilities.includes(capability)) return toast.error('请选择该 Space 已获授的 capability。')
    if (argsText.length > 8_192) return toast.error('参数不得超过 8 KiB。')
    let args: Record<string, unknown>
    try {
      const parsed: unknown = JSON.parse(argsText)
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error()
      args = parsed as Record<string, unknown>
    } catch {
      return toast.error('参数必须是 JSON object。')
    }
    const timeoutSeconds = Number(timeout)
    if (!Number.isInteger(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 60) return toast.error('超时必须为 1 到 60 秒。')
    try {
      await actions.submit.mutateAsync({ workspaceId, spaceId: space.id, data: { request_id: crypto.randomUUID(), capability, args, timeout_seconds: timeoutSeconds } })
      toast.success('任务已提交。')
    } catch (error) { toast.error(errorCode(error)) }
  }

  async function cancel() {
    if (!window.confirm('取消该任务？系统会等待清理完成后才显示为 cancelled。')) return
    try { await actions.cancel.mutateAsync({ workspaceId, spaceId: space.id }); toast.success('已请求取消任务。') } catch (error) { toast.error(errorCode(error)) }
  }

  async function close() {
    if (!window.confirm('关闭此 Space？关闭后不能提交新任务，浏览器实例保留会被释放。')) return
    try { await actions.close.mutateAsync({ workspaceId, spaceId: space.id }); toast.success('Space 已关闭。'); onClose() } catch (error) { toast.error(errorCode(error)) }
  }

  return (
    <Card className="min-h-0">
      <CardHeader className="border-b">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><CardTitle className="font-mono text-sm">{space.id}</CardTitle><CardDescription className="mt-1">实例 {space.browser_instance_id} · {space.owner_type}/{space.owner_id}</CardDescription></div>
          <div className="flex items-center gap-2"><Badge className={cn('border-0', statusClass(space.status))}>{space.status}</Badge><Button variant="ghost" size="icon-sm" aria-label="关闭详情" onClick={onClose}><X /></Button></div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-6 pt-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,.8fr)]">
        <section className="space-y-4">
          <div className="flex flex-wrap gap-2">{space.granted_capabilities.map((item) => <Badge key={item} variant="outline">{item}</Badge>)}</div>
          {space.status === 'closed' ? <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">该 Space 已关闭，不能再提交任务。</p> : <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
            <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-medium">提交受限 capability</h3><span className="text-xs text-muted-foreground">仅已授权名称 · JSON 不会在事件中回显</span></div>
            <div className="grid gap-3 sm:grid-cols-2"><label className="space-y-1 text-xs text-muted-foreground">Capability<select value={capability} onChange={(event) => setCapability(event.target.value)} className="h-9 w-full rounded-lg border bg-background px-2 text-sm text-foreground">{space.granted_capabilities.map((item) => <option key={item} value={item}>{item}</option>)}</select></label><label className="space-y-1 text-xs text-muted-foreground">超时（秒）<Input value={timeout} inputMode="numeric" onChange={(event) => setTimeout(event.target.value)} /></label></div>
            <label className="space-y-1 text-xs text-muted-foreground">有限参数（最大 8 KiB）<Textarea value={argsText} onChange={(event) => setArgsText(event.target.value)} spellCheck={false} className="min-h-28 font-mono text-xs" /></label>
            <div className="flex flex-wrap gap-2"><Button onClick={() => void submit()} disabled={Boolean(taskActive) || actions.submit.isPending || !space.granted_capabilities.length}><Send />提交任务</Button>{taskActive ? <Button variant="destructive" onClick={() => void cancel()} disabled={actions.cancel.isPending}><CircleStop />取消任务</Button> : null}<Button variant="outline" onClick={() => void close()} disabled={actions.close.isPending}><X />关闭 Space</Button></div>
          </div>}
          {task ? <div className="rounded-lg border p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-medium">最近任务 · {task.capability}</h3><Badge className={cn('border-0', statusClass(task.status))}>{task.status}</Badge></div>{task.error || task.error_code ? <p className="mt-2 text-sm text-destructive">{task.error?.code ?? task.error_code}: {task.error?.message ?? task.error_message}</p> : null}{task.result ? <pre className="mt-3 max-h-52 overflow-auto rounded-md bg-muted p-3 text-xs">{safeJson(task.result)}</pre> : null}</div> : null}
        </section>
        <section className="border-t pt-5 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0"><div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-medium">有序事件</h3><Button variant="ghost" size="icon-sm" aria-label="刷新事件" onClick={() => void events.refetch()}><RefreshCw /></Button></div>{events.isLoading ? <LoadingState rows={2} /> : events.isError ? <p className="text-sm text-destructive">{errorCode(events.error)}</p> : <EventLog events={events.data ?? []} />}</section>
      </CardContent>
    </Card>
  )
}

export function BrowserSpacesPanel({ workspaceId }: { workspaceId: string }) {
  const spaces = useBrowserSpaces(workspaceId)
  const actions = useBrowserSpaceActions()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [instanceId, setInstanceId] = useState('')
  const [ownerId, setOwnerId] = useState('')
  const [capabilities, setCapabilities] = useState('snapshot')
  const selected = spaces.data?.spaces.find((space) => space.id === selectedId) ?? null
  const available = spaces.data?.available_instances ?? []

  useEffect(() => { if (!selectedId && spaces.data?.spaces[0]) setSelectedId(spaces.data.spaces[0].id) }, [selectedId, spaces.data?.spaces])
  async function create() {
    const granted = capabilities.split(',').map((item) => item.trim()).filter(Boolean)
    if (!instanceId || !ownerId.trim() || !granted.length) return toast.error('请选择实例，并填写 owner 与至少一个 capability。')
    try {
      const space = await actions.create.mutateAsync({ workspaceId, data: { browser_instance_id: instanceId, owner_type: 'operator', owner_id: ownerId.trim(), granted_capabilities: granted } })
      setSelectedId(space.id)
      toast.success('Space 已创建并独占该浏览器实例。')
    } catch (error) { toast.error(errorCode(error)) }
  }

  if (spaces.isLoading) return <LoadingState rows={4} />
  if (spaces.isError) return <ErrorState message={errorCode(spaces.error)} />

  return <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
    <aside className="space-y-4"><Card><CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="size-4 text-primary" />新建 Space</CardTitle><CardDescription>每个实例只能被一个活动 Space 占用。</CardDescription></CardHeader><CardContent className="space-y-3"><label className="space-y-1 text-xs text-muted-foreground">已有 BrowserInstance<select value={instanceId} onChange={(event) => setInstanceId(event.target.value)} className="h-9 w-full rounded-lg border bg-background px-2 text-sm text-foreground" disabled={!available.length}><option value="">{available.length ? '选择已授权实例' : '后端尚未提供可用实例'}</option>{available.map((instance) => <option key={instance.id} value={instance.id}>{instance.label}</option>)}</select></label><label className="space-y-1 text-xs text-muted-foreground">Owner ID<Input value={ownerId} onChange={(event) => setOwnerId(event.target.value)} placeholder="已授权的 opaque identity" /></label><label className="space-y-1 text-xs text-muted-foreground">授予的 capability<Textarea value={capabilities} onChange={(event) => setCapabilities(event.target.value)} className="min-h-20 font-mono text-xs" placeholder="snapshot, navigate" /></label><Button className="w-full" onClick={() => void create()} disabled={!available.length || actions.create.isPending}><Plus />创建独占 Space</Button>{!available.length ? <p className="text-xs leading-5 text-muted-foreground">为保证不会复用操作员标签页，未收到后端允许实例清单时不能创建 Space。</p> : null}</CardContent></Card>
      <div className="space-y-2"><div className="flex items-center justify-between"><h2 className="text-sm font-medium">当前 Workspace</h2><Button variant="ghost" size="icon-sm" aria-label="刷新 Spaces" onClick={() => void spaces.refetch()}><RefreshCw /></Button></div>{spaces.data?.spaces.length ? spaces.data.spaces.map((space) => <button key={space.id} type="button" onClick={() => setSelectedId(space.id)} className={cn('w-full rounded-lg border p-3 text-left transition-colors hover:bg-muted/60', selectedId === space.id && 'border-primary bg-primary/5')}><div className="flex items-center justify-between gap-2"><span className="truncate font-mono text-xs">{space.id}</span><Badge className={cn('border-0', statusClass(space.status))}>{space.status}</Badge></div><p className="mt-1 truncate text-xs text-muted-foreground">{space.owner_type}/{space.owner_id}</p></button>) : <EmptyState title="还没有 Space" description="选择一个可用实例后创建独占执行边界。" />}</div></aside>
    <main>{selected ? <SpaceDetails workspaceId={workspaceId} space={selected} onClose={() => setSelectedId(null)} /> : <Card><CardContent className="py-12 text-center text-sm text-muted-foreground">选择一个 Space 以查看任务与事件。</CardContent></Card>}</main>
  </div>
}
