'use client'

import { useQueryClient } from '@tanstack/react-query'
import { Bot, Check, Loader2, Send, ShieldCheck, X } from 'lucide-react'
import { usePathname } from 'next/navigation'
import { FormEvent, KeyboardEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { apiClient } from '@/lib/api/client'
import type { ApiResponse } from '@/lib/api/types'
import { ROUTE_LABELS } from '@/lib/navigation'

type AgentMessage = {
  role: 'user' | 'assistant'
  content: string
}

type AgentProposal = {
  tool: string
  args: Record<string, unknown>
  summary: string
  diff: string
  work_item_id?: string | null
  workspace_id?: string | null
  proposal_version?: string | null
}

type AgentReply = {
  type: 'message' | 'proposal'
  content?: string | null
  proposal?: AgentProposal | null
}

export function GlobalAgentDock({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const pathname = usePathname()
  const queryClient = useQueryClient()
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [input, setInput] = useState('')
  const [proposal, setProposal] = useState<AgentProposal | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [confirming, setConfirming] = useState(false)

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault()
    const content = input.trim()
    if (!content || sending || proposal) return

    const nextMessages = [...messages, { role: 'user' as const, content }]
    setMessages(nextMessages)
    setInput('')
    setError(null)
    setSending(true)
    try {
      const searchParams = new URLSearchParams(window.location.search)
      const workspaceId = searchParams.get('workspace')
      const projectId = searchParams.get('project')
        ?? pathname.match(/^\/studio\/projects\/([^/]+)/)?.[1]
        ?? null
      const workflowId = searchParams.get('workflow')
      const sourceId = searchParams.get('source')
        ?? pathname.match(/^\/sources\/([^/]+)/)?.[1]
        ?? null
      const response = await apiClient.post<ApiResponse<AgentReply>>('/chat', {
        messages: nextMessages,
        context: {
          surface: ROUTE_LABELS[pathname] ?? pathname,
          pathname,
          search: searchParams.toString(),
          workspace_id: workspaceId,
          project_id: projectId,
          workflow_id: workflowId,
          source_id: sourceId,
        },
      })
      const reply = response.data.data
      if (reply.type === 'proposal' && reply.proposal) {
        setProposal(reply.proposal)
      } else {
        setMessages((current) => [
          ...current,
          { role: 'assistant', content: reply.content?.trim() || '没有返回内容。' },
        ])
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Agent 暂时不可用')
    } finally {
      setSending(false)
    }
  }

  async function confirmProposal() {
    if (!proposal || confirming) return
    setError(null)
    setConfirming(true)
    try {
      await apiClient.post('/chat/confirm', { proposal })
      setMessages((current) => [
        ...current,
        { role: 'assistant', content: `已执行：${proposal.summary}` },
      ])
      setProposal(null)
      await queryClient.invalidateQueries()
    } catch (reason) {
      const status = reason instanceof Error && 'status' in reason ? reason.status : undefined
      const message = reason instanceof Error ? reason.message : '操作执行失败'
      setError(
        status === 409
          ? `提案已失效或目标已变化：${message}。请拒绝后重新发起。`
          : message,
      )
    } finally {
      setConfirming(false)
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    void sendMessage()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="fixed bottom-4 right-4 top-auto left-auto flex h-[min(680px,calc(100vh-2rem))] w-[min(420px,calc(100vw-2rem))] max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden p-0 shadow-2xl"
        aria-label="全局 Agent"
      >
        <DialogHeader className="border-b px-4 py-3">
          <DialogTitle className="flex items-center gap-2">
            <Bot className="size-4 text-primary" aria-hidden />
            全局 Agent
          </DialogTitle>
          <DialogDescription>
            当前上下文：{ROUTE_LABELS[pathname] ?? pathname}。读取可直接执行，写入操作先生成确认提案。
            未明确指定 Workspace 时，仅在后端能解析出唯一授权范围时允许确认写操作。
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="min-h-0 flex-1">
          <div className="space-y-3 p-4" aria-live="polite">
            {messages.length === 0 ? (
              <div className="rounded-md border border-dashed p-4">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <ShieldCheck className="size-4 text-success" aria-hidden />
                  所有页面共用一个操作入口
                </div>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                  可以查询数据源、调度、任务和模型连接；涉及启停、触发或配置变更时会先展示差异。
                </p>
              </div>
            ) : null}
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={message.role === 'user'
                  ? 'ml-8 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground'
                  : 'mr-8 rounded-md border bg-muted/30 px-3 py-2 text-sm'}
              >
                {message.content}
              </div>
            ))}
            {sending ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground" role="status">
                <Loader2 className="size-3.5 animate-spin" aria-hidden />
                Agent 正在处理
              </div>
            ) : null}
            {proposal ? (
              <div className="rounded-md border border-warning/40 bg-warning/10 p-3">
                <div className="text-sm font-medium">待确认操作</div>
                <p className="mt-1 text-xs text-muted-foreground">{proposal.summary}</p>
                <div className="mt-3 rounded-xs border bg-background/70 p-2 font-mono text-2xs">
                  {proposal.diff}
                </div>
                <div className="mt-2 space-y-1 font-mono text-3xs text-muted-foreground">
                  <div>工作项：{proposal.work_item_id ?? '未生成'}</div>
                  <div>工作区：{proposal.workspace_id ?? '未绑定'}</div>
                  <div>提案版本：{proposal.proposal_version ?? '未生成'}</div>
                </div>
                <div className="mt-3 flex justify-end gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={confirming}
                    onClick={() => setProposal(null)}
                  >
                    <X aria-hidden />
                    拒绝
                  </Button>
                  <Button
                    size="sm"
                    disabled={
                      confirming
                      || !proposal.work_item_id
                      || !proposal.workspace_id
                      || !proposal.proposal_version
                    }
                    onClick={() => void confirmProposal()}
                  >
                    {confirming ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />}
                    确认执行
                  </Button>
                </div>
              </div>
            ) : null}
            {error ? <p className="text-xs text-destructive" role="alert">{error}</p> : null}
          </div>
        </ScrollArea>

        <form className="border-t p-4" onSubmit={(event) => void sendMessage(event)}>
          <Textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="告诉 Agent 你要查询或执行什么…"
            aria-label="给全局 Agent 的消息"
            className="max-h-36 min-h-20 resize-none rounded-xs"
            disabled={sending || confirming}
          />
          <div className="mt-2 flex items-center justify-between gap-3">
            <span className="text-3xs text-muted-foreground">Enter 发送 · Shift+Enter 换行</span>
            <Button type="submit" size="sm" disabled={!input.trim() || sending || confirming || Boolean(proposal)}>
              {sending ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
              发送
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
