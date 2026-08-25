'use client'

import { useState } from 'react'
import { Loader2, RotateCcw, ShieldAlert } from 'lucide-react'
import { toast } from 'sonner'

import { useRestartApi } from '@/lib/api/hooks'
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

export function RestartApiCard() {
  const [open, setOpen] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [justTriggered, setJustTriggered] = useState(false)
  const restartMutation = useRestartApi()

  const canConfirm = confirmText.trim() === CONFIRM_PHRASE

  const handleOpenChange = (next: boolean) => {
    setOpen(next)
    if (!next) setConfirmText('')
  }

  const handleConfirm = () => {
    if (!canConfirm) return
    restartMutation.mutate(undefined, {
      onSuccess: () => {
        toast.success('已发送重启指令，API 服务即将短暂离线')
        setJustTriggered(true)
        setConfirmText('')
        setOpen(false)
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
          重启 API 会重启承载整个后端的 Docker 容器 ——
          <strong className="text-foreground"> 影响当前所有已连接的用户和 Agent，不只是你这一个会话</strong>
          。所有进行中的请求与 WebSocket 连接都会中断。仅在确认部署配置（例如手动修改过 .env）需要生效时才执行。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {justTriggered ? (
          <p className="flex items-center gap-2 rounded-lg border border-dashed px-3 py-2.5 text-sm text-muted-foreground">
            <Loader2 className="size-3.5 shrink-0 animate-spin" />
            重启指令已发送。服务短暂离线后会自动恢复，期间的请求可能失败；刷新页面前此提示会一直保留。
          </p>
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
