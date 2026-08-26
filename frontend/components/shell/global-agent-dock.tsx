'use client'


import { useQueryClient } from '@tanstack/react-query'
import { Bot, ShieldCheck } from 'lucide-react'
import { usePathname } from 'next/navigation'
import { FormEvent, KeyboardEvent, useEffect, useState } from 'react'

import {
  AgentPromptBar,
  ApprovalCard,
  ThinkingTrace,
  ToolChip,
} from '@/components/agent-native/agent-primitives'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
  initialPrompt = '',
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialPrompt?: string
}) {
  const pathname = usePathname()
  const queryClient = useQueryClient()
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [input, setInput] = useState('')
  const [proposal, setProposal] = useState<AgentProposal | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [confirming, setConfirming] = useState(false)
  useEffect(() => {
    if (open && initialPrompt) {
      setInput(initialPrompt)
    }
  }, [initialPrompt, open])

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
          <div className="flex flex-wrap gap-1.5 pt-1" aria-label="Agent 能力状态">
            <ToolChip icon={Bot} label="当前页面" detail={ROUTE_LABELS[pathname] ?? pathname} />
            <ToolChip icon={ShieldCheck} label="写入保护" detail="需确认" tone="warning" />
          </div>
        </DialogHeader>

        <ScrollArea className="min-h-0 flex-1">
          <div className="space-y-3 p-4" aria-live="polite">
            {messages.length === 0 ? (
              <div className="rounded-lg border border-dashed p-4">
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
                  ? 'ml-8 rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground'
                  : 'mr-8 rounded-lg border bg-muted/30 px-3 py-2 text-sm'}
              >
                {message.content}
              </div>
            ))}
            {sending ? (
              <ThinkingTrace
                steps={['读取当前页面上下文', '整理可执行建议', '等待 Agent 回复']}
              />
            ) : null}
            {proposal ? (
              <ApprovalCard
                summary={proposal.summary}
                diff={proposal.diff}
                metadata={[
                  { label: '工具', value: proposal.tool },
                  { label: '工作项', value: proposal.work_item_id ?? '未生成' },
                  { label: '工作区', value: proposal.workspace_id ?? '未绑定' },
                  { label: '提案版本', value: proposal.proposal_version ?? '未生成' },
                ]}
                confirming={confirming}
                disabled={
                  !proposal.work_item_id
                  || !proposal.workspace_id
                  || !proposal.proposal_version
                }
                onReject={() => setProposal(null)}
                onConfirm={() => void confirmProposal()}
              />
            ) : null}
            {error ? <p className="text-xs text-destructive" role="alert">{error}</p> : null}
          </div>
        </ScrollArea>

        <AgentPromptBar
          value={input}
          onChange={setInput}
          onKeyDown={handleKeyDown}
          onSubmit={(event) => void sendMessage(event)}
          placeholder="描述你要查询或执行的事情…"
          disabled={sending || confirming || Boolean(proposal)}
          submitting={sending}
          footer={<>Enter 发送 · Shift+Enter 换行</>}
        />
      </DialogContent>
    </Dialog>
  )
}
