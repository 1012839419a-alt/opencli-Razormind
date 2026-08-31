'use client'

import { useState } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'

import { useAuth } from '@/components/auth/auth-provider'
import { BACKEND_HINT, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { RestartApiCard } from '@/components/system/restart-api-card'
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


  return (
    <PageContainer
      eyebrow="SYSTEM"
      title="系统设置"
      description="查看整套 OpenCLI 部署的状态、完成项与待处理项。"
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
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>浏览器与 Agent</CardTitle><CardDescription>查看执行资源是否准备好。</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <StatusRow label="默认 CDP" value={config.data.opencli_cdp_endpoint} />
              <StatusRow label="Agent Pool" value={config.data.agent_pool_endpoints.length ? `${config.data.agent_pool_endpoints.length} 个地址` : '未配置'} status={config.data.agent_pool_endpoints.length ? 'done' : 'pending'} />
              <StatusRow label="Fleet 网络" value={config.data.fleet_network_provider} />
              <StatusRow label="NetBird 模式" value={config.data.netbird_mode} />
              <StatusRow label="对外访问地址" value={config.data.public_url || '未配置'} status={config.data.public_url ? 'done' : 'pending'} />
              <Button variant="ghost" render={<Link href="/nodes" />}>查看节点</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>AI 与人机协作</CardTitle><CardDescription>展示模型与控制策略的当前状态。</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <StatusRow label="模型请求超时" value={`${config.data.llm_request_timeout_seconds} 秒`} />
              <StatusRow label="模型并发数" value={String(config.data.llm_max_concurrency)} />
              <StatusRow label="控制策略" value={config.data.control_mode === 'advisory' ? '建议模式' : '自动模式'} />
              <StatusRow label="全局暂停自动执行" value={config.data.control_kill_switch ? '已暂停' : '未暂停'} status={config.data.control_kill_switch ? 'pending' : 'done'} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>集成与密钥状态</CardTitle><CardDescription>只显示是否准备好，不在浏览器中暴露实际密钥。</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <StatusRow label="API / Fleet 访问令牌" value={config.data.api_auth_configured ? '已配置' : '未配置'} status={config.data.api_auth_configured ? 'done' : 'pending'} />
              <StatusRow label="凭证加密密钥" value={config.data.credential_encryption_configured ? '已配置' : '未配置'} status={config.data.credential_encryption_configured ? 'done' : 'pending'} />
              <StatusRow label="OIDC 组织登录" value={config.data.oidc_configured ? '已配置' : '未配置'} status={config.data.oidc_configured ? 'done' : 'pending'} />
              <StatusRow label="SMTP 通知" value={config.data.smtp_configured ? '已配置' : '未配置'} status={config.data.smtp_configured ? 'done' : 'pending'} />
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

        <RestartApiCard />
      </div>
    </PageContainer>
  )
}
