'use client'

import { useState } from 'react'
import { AlertTriangle, ShieldAlert, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'

import { useKillSwitch, useSetKillSwitch } from '@/lib/api/hooks'
import { cn } from '@/lib/utils'
import { BACKEND_HINT, ErrorState, LoadingState } from '@/components/shell/data-states'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

// Global actuator kill switch (issue 03). `engaged=true` short-circuits ALL
// Control Cycle execution on the next tick, unconditionally — this is a real
// safety control, not a settings toggle, so flipping it always goes through
// an explicit confirm dialog rather than a bare one-click switch.
export default function KillSwitchPage() {
  const { data, isLoading, isError, error } = useKillSwitch()
  const setKillSwitch = useSetKillSwitch()
  // Holds the target `engaged` value the confirm dialog is asking about;
  // null means the dialog is closed.
  const [confirmTarget, setConfirmTarget] = useState<boolean | null>(null)

  if (isLoading) return <LoadingState />
  if (isError) return <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
  if (!data) return <ErrorState message="未收到熔断开关状态" hint={BACKEND_HINT} />

  const engaged = data.engaged

  async function confirm() {
    if (confirmTarget === null) return
    try {
      const result = await setKillSwitch.mutateAsync(confirmTarget)
      setConfirmTarget(null)
      toast.success(
        result.engaged ? '熔断开关已接合 — 自动执行已被阻断' : '熔断开关已解除 — 自动执行恢复正常门禁评估',
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作失败')
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card className={cn(engaged && 'border-l-4 border-l-destructive')}>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <span
              className={cn(
                'mt-0.5 grid size-10 shrink-0 place-items-center rounded-lg',
                engaged ? 'bg-destructive/10 text-destructive' : 'bg-success/10 text-success',
              )}
            >
              {engaged ? <ShieldAlert className="size-5" aria-hidden /> : <ShieldCheck className="size-5" aria-hidden />}
            </span>
            <div>
              <CardTitle className="text-base">{engaged ? '熔断已接合' : '正常运行'}</CardTitle>
              <p className="mt-1 max-w-prose text-sm text-muted-foreground">
                {engaged
                  ? '控制回路的自动执行已被全局阻断——下一个周期起，任何 automatic 模式的动作都不会执行，直到手动解除。'
                  : '熔断开关未接合。动作是否真正执行仍取决于 CONTROL_MODE 以及其它门禁条件。'}
              </p>
            </div>
          </div>
          <Button
            variant={engaged ? 'outline' : 'destructive'}
            onClick={() => setConfirmTarget(!engaged)}
            disabled={setKillSwitch.isPending}
          >
            {engaged ? '解除熔断' : '立即熔断'}
          </Button>
        </CardHeader>
        <CardContent className="grid gap-4 border-t pt-4 sm:grid-cols-2">
          <div>
            <div className="text-xs text-muted-foreground">运行时覆盖</div>
            <div className="mt-1 text-sm">
              {data.runtime_override === null
                ? '未设置 — 跟随配置默认值'
                : data.runtime_override
                  ? '已手动接合（本次进程生命周期内有效）'
                  : '已手动解除（本次进程生命周期内有效）'}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">配置默认值（进程重启后回落到此值）</div>
            <div className="mt-1 text-sm">{data.config_default ? '默认熔断' : '默认运行'}</div>
          </div>
        </CardContent>
      </Card>

      <Dialog
        open={confirmTarget !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmTarget(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="size-4 text-destructive" aria-hidden />
              {confirmTarget ? '确认接合熔断开关' : '确认解除熔断开关'}
            </DialogTitle>
            <DialogDescription>
              {confirmTarget
                ? '接合后，控制回路会在下一个执行周期起立即停止所有 automatic 模式的动作，直到手动解除。这会影响正在运行的系统，请确认后再继续。'
                : '解除后，automatic 模式的动作将恢复接受 CONTROL_MODE 等其它门禁条件的评估。此操作本身不会立即触发任何执行。'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmTarget(null)} disabled={setKillSwitch.isPending}>
              取消
            </Button>
            <Button
              variant={confirmTarget ? 'destructive' : 'default'}
              onClick={() => void confirm()}
              disabled={setKillSwitch.isPending}
            >
              {setKillSwitch.isPending ? '正在提交…' : confirmTarget ? '确认熔断' : '确认解除'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
