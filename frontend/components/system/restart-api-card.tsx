'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CircleAlert, Loader2, RefreshCw, RotateCcw, ShieldAlert } from 'lucide-react'
import { toast } from 'sonner'

import { getHealth } from '@/lib/api/endpoints'
import { useRestartApi } from '@/lib/api/hooks'
import {
  apiRestartRecoveryRuns,
  orchestrateApiRestartRecovery,
  type ApiRestartRecoveryRun,
} from '@/lib/api/restart-orchestration'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'

// Deliberately not "restart" / "重启" — those are too easy to type by reflex.
// This is the strong, explicit confirmation the action's blast radius (the
// whole shared backend container, every connected user/agent) calls for.
const CONFIRM_PHRASE = 'RESTART'
const RESTART_REQUESTED_DISPLAY_MS = 250
const RESTART_RECOVERY_ATTEMPTS = 60

type RestartPhase = 'idle' | 'requested' | 'waiting' | 'recovered' | 'timeout'

export function RestartApiCard() {
  const [open, setOpen] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [phase, setPhase] = useState<RestartPhase>('idle')
  const pollingRef = useRef<ApiRestartRecoveryRun | null>(null)
  const baselineInstanceIdRef = useRef<string | undefined>(undefined)
  const outageObservedRef = useRef(false)
  const queryClient = useQueryClient()
  const restartMutation = useRestartApi()

  const canConfirm = confirmText.trim() === CONFIRM_PHRASE

  const handleOpenChange = (next: boolean) => {
    setOpen(next)
    if (!next) setConfirmText('')
  }

  useEffect(
    () => () => {
      const run = pollingRef.current
      if (run) apiRestartRecoveryRuns.cancel(run)
      pollingRef.current = null
    },
    [],
  )

  const checkRecovery = useCallback(
    async (waitForRestart: boolean, baselineInstanceId = baselineInstanceIdRef.current) => {
      if (pollingRef.current) return
      const run = apiRestartRecoveryRuns.begin()
      pollingRef.current = run

      try {
        if (waitForRestart) {
          baselineInstanceIdRef.current = baselineInstanceId
          outageObservedRef.current = false
          setPhase('requested')
          await new Promise<void>((resolve) => window.setTimeout(resolve, RESTART_REQUESTED_DISPLAY_MS))
          if (!apiRestartRecoveryRuns.isCurrent(run)) return
        }
        setPhase('waiting')

        const outcome = await orchestrateApiRestartRecovery({
          baselineInstanceId,
          initialOutageObserved: outageObservedRef.current,
          probe: (signal) => getHealth(undefined, signal),
          refreshActiveData: () => queryClient.invalidateQueries({ refetchType: 'active' }),
          signal: run.controller.signal,
          intervalMs: waitForRestart ? 750 : 2_500,
          maxAttempts: waitForRestart ? RESTART_RECOVERY_ATTEMPTS : 12,
        })
        outageObservedRef.current = outcome.outageObserved
        if (!apiRestartRecoveryRuns.isCurrent(run) || outcome.status === 'cancelled') return

        if (outcome.status === 'recovered') {
          setPhase('recovered')
          toast.success('API 已恢复，当前页面数据已刷新')
        } else {
          setPhase('timeout')
        }
      } catch (error) {
        if (apiRestartRecoveryRuns.isCurrent(run)) {
          setPhase('timeout')
          toast.error(error instanceof Error ? error.message : 'API 恢复检查失败')
        }
      } finally {
        apiRestartRecoveryRuns.finish(run)
        if (pollingRef.current?.token === run.token) pollingRef.current = null
      }
    },
    [queryClient],
  )

  const resetRecovery = () => {
    baselineInstanceIdRef.current = undefined
    outageObservedRef.current = false
    restartMutation.reset()
    setPhase('idle')
  }

  const handleConfirm = () => {
    if (!canConfirm) return
    restartMutation.mutate(undefined, {
      onSuccess: ({ baselineInstanceId }) => {
        toast.success('重启请求已接收，API 将短暂离线')
        setConfirmText('')
        setOpen(false)
        void checkRecovery(true, baselineInstanceId)
      },
      onError: (cause: Error) => toast.error(cause.message),
    })
  }

  return (
    <Card className="border-destructive/30 bg-destructive/5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm text-destructive">
          <ShieldAlert className="size-4" /> 危险操作
        </CardTitle>
        <CardDescription className="text-pretty">
          重启 API 会中断所有用户、Agent、请求与 WebSocket 连接。该操作只重启当前容器，不会重建容器，也不会应用宿主机
          <code>.env</code> 变更。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {phase !== 'idle' ? (
          <div className="space-y-3 rounded-lg border border-dashed px-3 py-2.5 text-sm" aria-live="polite">
            {phase === 'requested' ? (
              <p className="flex items-start gap-2 text-muted-foreground">
                <Loader2 className="mt-0.5 size-3.5 shrink-0 animate-spin" />
                重启请求已接收。连接可能短暂中断；恢复期间登录状态会保留。
              </p>
            ) : null}
            {phase === 'waiting' ? (
              <p className="flex items-start gap-2 text-muted-foreground">
                <Loader2 className="mt-0.5 size-3.5 shrink-0 animate-spin" />
                API 暂不可用或正在启动。系统会在限定时间内逐次检查，不会并发重试。
              </p>
            ) : null}
            {phase === 'recovered' ? (
              <div className="space-y-3">
                <p className="flex items-start gap-2 text-emerald-700 dark:text-emerald-300">
                  <CheckCircle2 className="mt-0.5 size-3.5 shrink-0" />
                  API 已恢复，当前页面数据已刷新。注意：这不代表宿主机配置已经生效；若修改了部署设置，请重建容器并重新验证身份。
                </p>
                <Button variant="outline" size="sm" onClick={resetRecovery}>
                  <RotateCcw className="size-3.5" /> 再次重启
                </Button>
              </div>
            ) : null}
            {phase === 'timeout' ? (
              <div className="space-y-3">
                <p className="flex items-start gap-2 text-amber-700 dark:text-amber-300">
                  <CircleAlert className="mt-0.5 size-3.5 shrink-0" />
                  在限定时间内未确认恢复。请检查 <code>docker compose ps</code> 与 API 日志后重试；登录状态仍已保留。
                </p>
                <Button variant="outline" size="sm" onClick={() => void checkRecovery(false)}>
                  <RefreshCw className="size-3.5" /> 重新检查
                </Button>
              </div>
            ) : null}
          </div>
        ) : (
          <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogTrigger render={<Button variant="destructive" size="sm" />}>
              <RotateCcw className="size-3.5" />
              重启 API 服务
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2 text-destructive">
                  <ShieldAlert className="size-4" /> 确认重启 API 服务
                </DialogTitle>
                <DialogDescription className="text-pretty">
                  这会重启整个后端容器，
                  <strong className="text-foreground">所有用户和 Agent 的连接都会中断</strong>
                  ，不仅是你当前的会话。此操作无法撤销。
                </DialogDescription>
              </DialogHeader>

              <Field>
                <FieldLabel htmlFor="restart-confirm-input">
                  请输入 <span className="font-mono font-semibold">{CONFIRM_PHRASE}</span> 以确认
                </FieldLabel>
                <Input
                  id="restart-confirm-input"
                  autoComplete="off"
                  autoFocus
                  value={confirmText}
                  onChange={(event) => setConfirmText(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && canConfirm) handleConfirm()
                  }}
                  placeholder={CONFIRM_PHRASE}
                />
                <FieldDescription>区分大小写，需完全匹配。</FieldDescription>
              </Field>

              <DialogFooter>
                <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
                <Button
                  variant="destructive"
                  disabled={!canConfirm || restartMutation.isPending}
                  onClick={handleConfirm}
                >
                  {restartMutation.isPending ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <RotateCcw className="size-3.5" />
                  )}
                  {restartMutation.isPending ? '正在触发…' : '确认重启'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </CardContent>
    </Card>
  )
}
