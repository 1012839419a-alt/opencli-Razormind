'use client'

import { useState } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'

import { useAuth } from '@/components/auth/auth-provider'
import { BACKEND_HINT, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useSystemConfig } from '@/lib/api/hooks'

type StatusRowProps = {
  label: string
  value: string
  status?: 'done' | 'pending' | 'readonly'
}

function StatusRow({ label, value, status = 'readonly' }: StatusRowProps) {
  const statusLabel = status === 'done' ? '已配置' : status === 'pending' ? '待配置' : '只读'
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border px-3 py-2.5">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="flex items-center gap-2 text-right text-sm font-medium">
        <span className="max-w-64 truncate">{value}</span>
        <Badge variant={status === 'done' ? 'secondary' : 'outline'}>{statusLabel}</Badge>
      </span>
    </div>
  )
}

function requestAgent(prompt: string) {
  window.dispatchEvent(new CustomEvent('open-global-agent', { detail: { prompt } }))
}

export default function SystemSettingsPage() {
  const config = useSystemConfig()
  const { changePassword } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [savingPassword, setSavingPassword] = useState(false)

  async function savePassword(event: React.FormEvent) {
    event.preventDefault()
    if (newPassword !== confirmPassword) {
      toast.error('两次输入的新密码不一致')
      return
    }
    setSavingPassword(true)
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      toast.success('密码已更新')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '密码更新失败')
    } finally {
      setSavingPassword(false)
    }
  }

  if (config.isLoading) return <LoadingState />
  if (config.isError || !config.data) {
    return <ErrorState message={(config.error as Error)?.message} hint={BACKEND_HINT} />
  }

  const runtimePrompt = '请检查当前 OpenCLI 的任务执行模式、调度器、并发数、超时和时区；列出未配置项，并在我确认后完成必要配置。'
  const agentPrompt = '请检查浏览器节点、Agent Pool、CDP 地址和 Fleet 网络；告诉我哪些节点可用、哪些配置缺失，并在我确认后修复。'
  const collaborationPrompt = '请检查模型连接、AI 并发限制、控制策略和全局暂停开关；用人能看懂的方式说明当前状态，并给出需要我确认的变更。'

  return (
    <PageContainer
      eyebrow="SYSTEM"
      title="系统设置"
      description="这里主要展示系统状态。需要变更时，让 Agent 读取上下文并协助配置。"
      actions={<Button onClick={() => requestAgent('请完整检查这套 OpenCLI 部署的系统设置，告诉我哪些已完成、哪些未完成。')}>让 Agent 检查全部</Button>}
    >
      <div className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle>系统概览</CardTitle>
            <CardDescription>用户先看结果，不需要先理解环境变量和部署参数。</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">应用环境</p><p className="mt-1 font-medium">{config.data.app_env}</p></div>
            <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">数据库</p><p className="mt-1 font-medium">{config.data.database_kind}</p></div>
            <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">镜像版本</p><p className="mt-1 font-mono text-xs">{config.data.image_tag}</p></div>
            <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">调试模式</p><p className="mt-1 font-medium">{config.data.debug ? '开启' : '关闭'}</p></div>
          </CardContent>
        </Card>

        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader><CardTitle>任务与执行</CardTitle><CardDescription>当前配置结果与待处理项。</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <StatusRow label="采集执行位置" value={config.data.collection_mode === 'local' ? '本机执行' : '远程 Agent 执行'} status="done" />
              <StatusRow label="调度编排器" value={config.data.collection_orchestrator} status="done" />
              <StatusRow label="最大并发任务" value={String(config.data.local_max_concurrent_pipelines)} />
              <StatusRow label="OpenCLI 超时" value={`${config.data.opencli_timeout} 秒`} />
              <StatusRow label="默认时区" value={config.data.default_timezone} />
              <Button variant="outline" onClick={() => requestAgent(runtimePrompt)}>让 Agent 配置执行参数</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>浏览器与 Agent</CardTitle><CardDescription>查看执行资源是否准备好，具体修改交给 Agent。</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <StatusRow label="默认 CDP" value={config.data.opencli_cdp_endpoint} />
              <StatusRow label="Agent Pool" value={config.data.agent_pool_endpoints.length ? `${config.data.agent_pool_endpoints.length} 个地址` : '未配置'} status={config.data.agent_pool_endpoints.length ? 'done' : 'pending'} />
              <StatusRow label="Fleet 网络" value={config.data.fleet_network_provider} />
              <StatusRow label="NetBird 模式" value={config.data.netbird_mode} />
              <StatusRow label="对外访问地址" value={config.data.public_url || '未配置'} status={config.data.public_url ? 'done' : 'pending'} />
              <div className="flex gap-2"><Button variant="outline" onClick={() => requestAgent(agentPrompt)}>让 Agent 检查节点</Button><Button variant="ghost" render={<Link href="/nodes" />}>查看节点</Button></div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>AI 与人机协作</CardTitle><CardDescription>模型与控制策略由 Agent 解释，人只确认有影响的变更。</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <StatusRow label="模型请求超时" value={`${config.data.llm_request_timeout_seconds} 秒`} />
              <StatusRow label="模型并发数" value={String(config.data.llm_max_concurrency)} />
              <StatusRow label="控制策略" value={config.data.control_mode === 'advisory' ? '建议模式' : '自动模式'} />
              <StatusRow label="全局暂停自动执行" value={config.data.control_kill_switch ? '已暂停' : '未暂停'} status={config.data.control_kill_switch ? 'pending' : 'done'} />
              <Button variant="outline" onClick={() => requestAgent(collaborationPrompt)}>让 Agent 检查协作策略</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>集成与密钥状态</CardTitle><CardDescription>只显示是否准备好，不在浏览器中暴露实际密钥。</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <StatusRow label="API / Fleet 访问令牌" value={config.data.api_auth_configured ? '已配置' : '未配置'} status={config.data.api_auth_configured ? 'done' : 'pending'} />
              <StatusRow label="凭证加密密钥" value={config.data.credential_encryption_configured ? '已配置' : '未配置'} status={config.data.credential_encryption_configured ? 'done' : 'pending'} />
              <StatusRow label="OIDC 组织登录" value={config.data.oidc_configured ? '已配置' : '未配置'} status={config.data.oidc_configured ? 'done' : 'pending'} />
              <StatusRow label="SMTP 通知" value={config.data.smtp_configured ? '已配置' : '未配置'} status={config.data.smtp_configured ? 'done' : 'pending'} />
              <Button variant="outline" onClick={() => requestAgent('请检查模型、OIDC、SMTP 和通知渠道配置，列出哪些集成可以使用，哪些还没有配置。')}>让 Agent 检查集成</Button>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader><CardTitle>管理员账户</CardTitle><CardDescription>账户密码属于安全边界，仍保留明确的人工确认表单。</CardDescription></CardHeader>
          <CardContent>
            <form className="max-w-xl space-y-5" onSubmit={savePassword}>
              <FieldGroup>
                <Field><FieldLabel htmlFor="current-password">当前密码</FieldLabel><Input id="current-password" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></Field>
                <Field><FieldLabel htmlFor="new-password">新密码</FieldLabel><Input id="new-password" type="password" autoComplete="new-password" minLength={6} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /><FieldDescription>至少 6 个字符。</FieldDescription></Field>
                <Field><FieldLabel htmlFor="confirm-password">确认新密码</FieldLabel><Input id="confirm-password" type="password" autoComplete="new-password" minLength={6} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required /></Field>
              </FieldGroup>
              <Button type="submit" disabled={savingPassword}>{savingPassword ? '保存中…' : '保存密码'}</Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  )
}
