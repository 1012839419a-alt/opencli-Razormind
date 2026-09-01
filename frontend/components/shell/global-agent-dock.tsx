'use client'

import { useQueryClient } from '@tanstack/react-query'
import { Archive, Bot, Check, Loader2, Plus, Send, ShieldCheck, X } from 'lucide-react'
import { usePathname, useSearchParams } from 'next/navigation'
import { FormEvent, KeyboardEvent, useEffect, useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { apiClient } from '@/lib/api/client'
import {
  useAgentConversation,
  useAgentConversations,
  useCloseAgentConversation,
  useCreateAgentConversation,
  useMyWorkspaces,
  useSendAgentConversationMessage,
} from '@/lib/api/hooks'
import type { AgentConversationContext, AgentProposal } from '@/lib/api/types'
import { ROUTE_LABELS } from '@/lib/navigation'

function getSessionStorageKey(workspaceId: string) {
  return `opencli:agent-session:${workspaceId}`
}

function createRequestId() {
  return globalThis.crypto?.randomUUID?.() ?? `agent-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function GlobalAgentDock({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const queryClient = useQueryClient()
  const [input, setInput] = useState('')
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null)
  const [dismissedProposalSequence, setDismissedProposalSequence] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  const workspaces = useMyWorkspaces()
  const explicitWorkspaceId = searchParams.get('workspace')
  const workspaceId = explicitWorkspaceId ?? (workspaces.data?.length === 1 ? workspaces.data[0].id : null)
  const workspaceIsAmbiguous = !explicitWorkspaceId && !workspaces.isLoading && (workspaces.data?.length ?? 0) !== 1
  const context = useMemo<AgentConversationContext>(() => ({
    project_id: searchParams.get('project') ?? pathname.match(/^\/studio\/projects\/([^/]+)/)?.[1] ?? null,
    workflow_id: searchParams.get('workflow'),
    run_id: searchParams.get('run'),
    source_id: searchParams.get('source') ?? pathname.match(/^\/sources\/([^/]+)/)?.[1] ?? null,
    surface: ROUTE_LABELS[pathname] ?? pathname,
  }), [pathname, searchParams])

  const conversations = useAgentConversations(workspaceId, open && !workspaceIsAmbiguous)
  const conversation = useAgentConversation(selectedConversationId, open && !workspaceIsAmbiguous)
  const createConversation = useCreateAgentConversation()
  const sendMessageMutation = useSendAgentConversationMessage()
  const closeConversation = useCloseAgentConversation()
  const sending = createConversation.isPending || sendMessageMutation.isPending

  // The API owns all data. localStorage holds only a Workspace-scoped UUID pointer.
  useEffect(() => {
    if (!workspaceId || !conversations.data) return
    const storedId = window.localStorage.getItem(getSessionStorageKey(workspaceId))
    const nextId = conversations.data.some((item) => item.id === storedId) ? storedId : conversations.data[0]?.id ?? null
    setSelectedConversationId(nextId)
    setDismissedProposalSequence(null)
  }, [workspaceId, conversations.data])

  useEffect(() => {
    if (!workspaceId) return
    const key = getSessionStorageKey(workspaceId)
    if (selectedConversationId) window.localStorage.setItem(key, selectedConversationId)
    else window.localStorage.removeItem(key)
  }, [selectedConversationId, workspaceId])

  const pendingProposal = conversation.data?.turns.slice().reverse().find((turn) => (
    turn.status === 'proposal' && turn.response?.proposal && turn.sequence !== dismissedProposalSequence
  ))
  const proposal = pendingProposal?.response?.proposal as AgentProposal | undefined
  const isClosed = conversation.data?.status === 'closed'

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault()
    const content = input.trim()
    if (!content || sending || proposal || !workspaceId || workspaceIsAmbiguous || isClosed) return
    setInput('')
    setError(null)
    try {
      let conversationId = selectedConversationId
      if (!conversationId) {
        const created = await createConversation.mutateAsync({ workspace_id: workspaceId, context })
        conversationId = created.id
        setSelectedConversationId(conversationId)
      }
      await sendMessageMutation.mutateAsync({ conversationId, data: { request_id: createRequestId(), content, context } })
      await queryClient.invalidateQueries({ queryKey: ['agent-conversation', conversationId] })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Agent 暂时不可用')
    }
  }

  async function confirmProposal() {
    if (!proposal || !pendingProposal || confirming) return
    setError(null)
    setConfirming(true)
    try {
      await apiClient.post('/chat/confirm', { proposal })
      setDismissedProposalSequence(pendingProposal.sequence)
      await queryClient.invalidateQueries()
    } catch (reason) {
      const status = reason instanceof Error && 'status' in reason ? reason.status : undefined
      const message = reason instanceof Error ? reason.message : '操作执行失败'
      setError(status === 409 ? `提案已失效或目标已变化：${message}。请拒绝后重新发起。` : message)
    } finally {
      setConfirming(false)
    }
  }

  async function handleCloseConversation() {
    if (!selectedConversationId || closeConversation.isPending) return
    setError(null)
    try {
      await closeConversation.mutateAsync(selectedConversationId)
      if (workspaceId) window.localStorage.removeItem(getSessionStorageKey(workspaceId))
      setSelectedConversationId(null)
      setDismissedProposalSequence(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '关闭会话失败')
    }
  }

  function handleNewConversation() {
    if (workspaceId) window.localStorage.removeItem(getSessionStorageKey(workspaceId))
    setSelectedConversationId(null)
    setDismissedProposalSequence(null)
    setError(null)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    void sendMessage()
  }

  const visibleError = error || (conversations.error ?? conversation.error as Error | null)?.message

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 sm:max-w-md" aria-label="全局 Agent">
        <SheetHeader className="border-b">
          <div className="flex items-center justify-between gap-3">
            <SheetTitle className="flex items-center gap-2"><Bot className="size-4 text-primary" aria-hidden />全局 Agent</SheetTitle>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon-sm" onClick={handleNewConversation} disabled={!workspaceId || workspaceIsAmbiguous} aria-label="新建 Agent 会话"><Plus aria-hidden /></Button>
              <Button variant="ghost" size="icon-sm" onClick={() => void handleCloseConversation()} disabled={!selectedConversationId || isClosed || closeConversation.isPending} aria-label="关闭 Agent 会话">{closeConversation.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Archive aria-hidden />}</Button>
            </div>
          </div>
          <SheetDescription>当前上下文：{ROUTE_LABELS[pathname] ?? pathname}。路由变更只会绑定下一条消息，不会改写历史会话。</SheetDescription>
          {workspaceId && conversations.data?.length ? (
            <select aria-label="选择 Agent 会话" className="mt-2 h-8 w-full rounded-md border bg-background px-2 text-xs" value={selectedConversationId ?? ''} onChange={(event) => { setSelectedConversationId(event.target.value || null); setDismissedProposalSequence(null) }}>
              {conversations.data.map((item) => <option key={item.id} value={item.id}>{item.title || `会话 ${item.id.slice(0, 8)}`}</option>)}
            </select>
          ) : null}
        </SheetHeader>

        <ScrollArea className="min-h-0 flex-1"><div className="space-y-3 p-4" aria-live="polite">
          {workspaceIsAmbiguous ? <div className="rounded-md border border-warning/40 bg-warning/10 p-4 text-sm">请先在页面 URL 中选择 Workspace，再使用持久化 Agent 会话。系统不会把会话静默写入不明确的范围。</div> : null}
          {conversations.isLoading || conversation.isLoading ? <div className="flex items-center gap-2 text-xs text-muted-foreground" role="status"><Loader2 className="size-3.5 animate-spin" aria-hidden />正在恢复会话</div> : null}
          {!workspaceIsAmbiguous && !conversation.data && !conversations.isLoading ? <div className="rounded-md border border-dashed p-4"><div className="flex items-center gap-2 text-sm font-medium"><ShieldCheck className="size-4 text-success" aria-hidden />新会话将在发送第一条消息时创建</div><p className="mt-2 text-xs leading-5 text-muted-foreground">服务端保存对话、提案和不可变上下文快照；此浏览器只保存当前选中的会话。</p></div> : null}
          {conversation.data?.turns.map((turn) => <div key={turn.sequence} className="space-y-2"><div className="ml-8 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground">{turn.user_content}</div>{turn.response?.type === 'message' ? <div className="mr-8 rounded-md border bg-muted/30 px-3 py-2 text-sm">{turn.response.content?.trim() || '没有返回内容。'}</div> : null}{turn.status === 'failed' ? <p className="mr-8 text-xs text-destructive">{turn.error_message || 'Agent 未能完成此消息。'}</p> : null}</div>)}
          {sending ? <div className="flex items-center gap-2 text-xs text-muted-foreground" role="status"><Loader2 className="size-3.5 animate-spin" aria-hidden />Agent 正在处理</div> : null}
          {proposal ? <div className="rounded-md border border-warning/40 bg-warning/10 p-3"><div className="text-sm font-medium">待确认操作</div><p className="mt-1 text-xs text-muted-foreground">{proposal.summary}</p><div className="mt-3 rounded-xs border bg-background/70 p-2 font-mono text-2xs">{proposal.diff}</div><div className="mt-2 space-y-1 font-mono text-3xs text-muted-foreground"><div>工作项：{proposal.work_item_id ?? '未生成'}</div><div>工作区：{proposal.workspace_id ?? '未绑定'}</div><div>提案版本：{proposal.proposal_version ?? '未生成'}</div></div><div className="mt-3 flex justify-end gap-2"><Button variant="ghost" size="sm" disabled={confirming} onClick={() => setDismissedProposalSequence(pendingProposal?.sequence ?? null)}><X aria-hidden />拒绝</Button><Button size="sm" disabled={confirming || !proposal.work_item_id || !proposal.workspace_id || !proposal.proposal_version} onClick={() => void confirmProposal()}>{confirming ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />}确认执行</Button></div></div> : null}
          {visibleError ? <p className="text-xs text-destructive" role="alert">{visibleError}</p> : null}
        </div></ScrollArea>

        <form className="border-t p-4" onSubmit={(event) => void sendMessage(event)}><Textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={handleKeyDown} placeholder={workspaceIsAmbiguous ? '请先选择 Workspace' : isClosed ? '此会话已关闭，请新建会话' : '告诉 Agent 你要查询或执行什么…'} aria-label="给全局 Agent 的消息" className="max-h-36 min-h-20 resize-none rounded-xs" disabled={sending || confirming || workspaceIsAmbiguous || isClosed} /><div className="mt-2 flex items-center justify-between gap-3"><span className="text-3xs text-muted-foreground">Enter 发送 · Shift+Enter 换行</span><Button type="submit" size="sm" disabled={!input.trim() || sending || confirming || Boolean(proposal) || workspaceIsAmbiguous || isClosed}>{sending ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}发送</Button></div></form>
      </SheetContent>
    </Sheet>
  )
}
