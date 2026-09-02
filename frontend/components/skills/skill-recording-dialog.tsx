'use client'

import { useEffect, useMemo, useState } from 'react'
import { CircleStop, Play, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import {
  useChromePool,
  useDistillSkill,
  useRecordStart,
  useRecordStop,
} from '@/lib/api/hooks'
import { BACKEND_HINT, ErrorState } from '@/components/shell/data-states'
import { Badge } from '@/components/ui/badge'
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

type RecordingStage = 'setup' | 'recording' | 'review'

export function SkillRecordingDialog() {
  const pool = useChromePool()
  const startRecording = useRecordStart()
  const stopRecording = useRecordStop()
  const distillSkill = useDistillSkill()
  const [open, setOpen] = useState(false)
  const [stage, setStage] = useState<RecordingStage>('setup')
  const [domain, setDomain] = useState('')
  const [capability, setCapability] = useState('')
  const [cdpEndpoint, setCdpEndpoint] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null)
  const [stopStatus, setStopStatus] = useState('success')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const endpoints = useMemo(
    () => pool.data?.endpoints.filter((endpoint) => endpoint.available) ?? [],
    [pool.data?.endpoints],
  )

  useEffect(() => {
    if (!cdpEndpoint && endpoints.length > 0) setCdpEndpoint(endpoints[0].url)
  }, [cdpEndpoint, endpoints])

  useEffect(() => {
    if (!open || stage !== 'recording') return
    const warnOnLeave = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = '录制仍在进行，离开会终止本次录制。'
    }
    window.addEventListener('beforeunload', warnOnLeave)
    return () => window.removeEventListener('beforeunload', warnOnLeave)
  }, [open, stage])

  function reset() {
    setStage('setup')
    setDomain('')
    setCapability('')
    setCdpEndpoint('')
    setSessionId(null)
    setTrace(null)
    setStopStatus('success')
    setNote('')
    setError(null)
  }

  async function start() {
    if (!domain.trim() || !capability.trim()) return
    setError(null)
    try {
      const result = await startRecording.mutateAsync({
        domain: domain.trim(),
        capability: capability.trim(),
        cdp_endpoint: cdpEndpoint.trim() || undefined,
      })
      setSessionId(result.session_id)
      setCdpEndpoint(result.cdp_endpoint)
      setStage('recording')
      toast.success('录制已开始')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法开始录制')
    }
  }

  async function stop() {
    if (!sessionId) return
    setError(null)
    try {
      const result = await stopRecording.mutateAsync({
        sessionId,
        data: { status: stopStatus, note: note.trim() || undefined },
      })
      setTrace(result)
      setSessionId(null)
      setStage('review')
      toast.success('录制已停止，请先审核 trace')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法停止录制')
    }
  }

  async function distill() {
    if (!trace) return
    setError(null)
    try {
      const skill = await distillSkill.mutateAsync({
        trace,
        domain: domain.trim() || undefined,
        capability: capability.trim() || undefined,
      })
      toast.success(`技能已创建，版本 v${skill.version}`)
      setOpen(false)
      reset()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '技能蒸馏失败')
    }
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => {
      if (!nextOpen && stage === 'recording') {
        setError('录制仍在进行，请先停止录制；关闭窗口不会伪造完成状态。')
        return
      }
      setOpen(nextOpen)
      if (!nextOpen) reset()
    }}>
      <DialogTrigger render={<Button />}>
        <Play className="size-4" />
        录制新技能
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>录制并蒸馏技能</DialogTitle>
          <DialogDescription>
            连接浏览器完成演示，停止后先查看真实 journey_trace_v1，再明确创建 Skill v1。关闭或刷新录制窗口会提示未完成状态。
          </DialogDescription>
        </DialogHeader>

        {stage === 'setup' ? (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5 text-sm">
                领域
                <Input value={domain} onChange={(event) => setDomain(event.target.value)} placeholder="例如 finance" required />
              </label>
              <label className="space-y-1.5 text-sm">
                能力
                <Input value={capability} onChange={(event) => setCapability(event.target.value)} placeholder="例如 daily-report" required />
              </label>
            </div>
            <label className="block space-y-1.5 text-sm">
              Browser endpoint
              {endpoints.length > 0 ? (
                <Select value={cdpEndpoint} onValueChange={(value) => value && setCdpEndpoint(value)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {endpoints.map((endpoint) => (
                      <SelectItem key={endpoint.url} value={endpoint.url}>{endpoint.url}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input value={cdpEndpoint} onChange={(event) => setCdpEndpoint(event.target.value)} placeholder="可选，留空使用默认浏览器池" />
              )}
            </label>
            {pool.isError ? <p className="text-xs text-warning">浏览器池状态不可用，可手动输入 CDP endpoint，开始时由后端再次校验。</p> : null}
            <Button onClick={() => void start()} disabled={startRecording.isPending || !domain.trim() || !capability.trim()}>
              <Play className="size-4" />
              {startRecording.isPending ? '连接中…' : '开始录制'}
            </Button>
          </div>
        ) : stage === 'recording' ? (
          <div className="space-y-4">
            <div className="rounded-md border border-warning/40 bg-warning/10 p-3">
              <div className="flex items-center gap-2 text-warning">
                <span className="size-2 animate-pulse rounded-full bg-warning" />
                <span className="font-medium">录制进行中</span>
                <Badge variant="outline">{domain} / {capability}</Badge>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">Browser endpoint: <span className="font-mono">{cdpEndpoint}</span></p>
            </div>
            <p className="text-sm text-muted-foreground">现在可以在已连接的浏览器中完成操作演示。结束后回到这里停止录制，系统不会在停止时自动创建技能。</p>
            <div className="grid gap-4 sm:grid-cols-[10rem_minmax(0,1fr)]">
              <label className="space-y-1.5 text-sm">
                结果
                <Select value={stopStatus} onValueChange={(value) => value && setStopStatus(value)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="success">成功</SelectItem>
                    <SelectItem value="failed">失败</SelectItem>
                  </SelectContent>
                </Select>
              </label>
              <label className="space-y-1.5 text-sm">
                备注
                <Input value={note} onChange={(event) => setNote(event.target.value)} placeholder="可选，记录这次演示意图" />
              </label>
            </div>
            <Button variant="destructive" onClick={() => void stop()} disabled={stopRecording.isPending}>
              <CircleStop className="size-4" />
              {stopRecording.isPending ? '停止中…' : '停止并审核 trace'}
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Badge variant="secondary">待审核</Badge>
              <span className="text-sm text-muted-foreground">录制已结束，确认 trace 内容后才能创建 Skill v1。</span>
            </div>
            <pre className="max-h-80 overflow-auto rounded-md border bg-muted/25 p-3 font-mono text-xs leading-5">
              {JSON.stringify(trace ?? {}, null, 2)}
            </pre>
            <Button onClick={() => void distill()} disabled={distillSkill.isPending || !trace}>
              <Sparkles className="size-4" />
              {distillSkill.isPending ? '蒸馏中…' : '确认并创建 Skill v1'}
            </Button>
          </div>
        )}

        {error ? <ErrorState message={error} hint={BACKEND_HINT} /> : null}
        <DialogFooter>
          {stage !== 'recording' ? (
            <Button variant="outline" onClick={() => setOpen(false)}>取消</Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
