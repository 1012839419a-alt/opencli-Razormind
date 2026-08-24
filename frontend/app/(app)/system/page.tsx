'use client'

import { useEffect, useState } from 'react'
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
import { useSystemConfig, useUpdateSystemConfig } from '@/lib/api/hooks'
import type { SystemConfig } from '@/lib/api/types'

function configuredLabel(value: boolean) {
  return value ? '已配置' : '未配置'
}

function StatusBadge({ configured }: { configured: boolean }) {
  return <Badge variant={configured ? 'secondary' : 'outline'}>{configuredLabel(configured)}</Badge>
}

export default function SystemSettingsPage() {
  const config = useSystemConfig()
  const updateConfig = useUpdateSystemConfig()
  const { changePassword } = useAuth()
  const [form, setForm] = useState<Pick<SystemConfig, 'collection_mode' | 'collection_orchestrator' | 'local_max_concurrent_pipelines' | 'opencli_timeout' | 'default_timezone' | 'public_url' | 'fleet_network_provider' | 'netbird_mode' | 'opencli_cdp_endpoint' | 'agent_pool_endpoints' | 'llm_request_timeout_seconds' | 'llm_max_concurrency' | 'control_mode' | 'control_kill_switch'>>({
    collection_mode: 'local',
    collection_orchestrator: 'admin',
    local_max_concurrent_pipelines: 8,
    opencli_timeout: 120,
    default_timezone: 'UTC',
    public_url: '',
    fleet_network_provider: 'lan',
    netbird_mode: 'off',
    opencli_cdp_endpoint: 'http://localhost:9222',
    agent_pool_endpoints: [],
    llm_request_timeout_seconds: 120,
    llm_max_concurrency: 4,
    control_mode: 'advisory',
    control_kill_switch: false,
  })
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [savingPassword, setSavingPassword] = useState(false)

  useEffect(() => {
    if (!config.data) return
    setForm({
      collection_mode: config.data.collection_mode,
      collection_orchestrator: config.data.collection_orchestrator,
      local_max_concurrent_pipelines: config.data.local_max_concurrent_pipelines,
      opencli_timeout: config.data.opencli_timeout,
      default_timezone: config.data.default_timezone,
      public_url: config.data.public_url,
      fleet_network_provider: config.data.fleet_network_provider,
      netbird_mode: config.data.netbird_mode,
      opencli_cdp_endpoint: config.data.opencli_cdp_endpoint,
      agent_pool_endpoints: config.data.agent_pool_endpoints,
      llm_request_timeout_seconds: config.data.llm_request_timeout_seconds,
      llm_max_concurrency: config.data.llm_max_concurrency,
      control_mode: config.data.control_mode,
      control_kill_switch: config.data.control_kill_switch,
    })
  }, [config.data])

  function setField<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  async function saveSystemConfig() {
    try {
      await updateConfig.mutateAsync({
        ...form,
        agent_pool_endpoints: form.agent_pool_endpoints.join(','),
      })
      toast.success('系统设置已保存')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '系统设置保存失败')
    }
  }

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
      description="管理整套 OpenCLI 部署、执行资源、人机协作策略与管理员账户。"
      actions={<Button onClick={() => void saveSystemConfig()} disabled={updateConfig.isPending}>{updateConfig.isPending ? '保存中…' : '保存全部设置'}</Button>}
    >
      <div className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle>系统概览</CardTitle>
            <CardDescription>先确认当前部署状态，再调整下面的运行参数。</CardDescription>
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
            <CardHeader><CardTitle>任务与执行</CardTitle><CardDescription>控制采集任务如何运行，以及单机资源上限。</CardDescription></CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5 text-sm"><span className="font-medium">采集执行位置</span><select value={form.collection_mode} onChange={(event) => setField('collection_mode', event.target.value as typeof form.collection_mode)} className="h-9 w-full rounded-lg border bg-background px-3"><option value="local">本机执行</option><option value="agent">远程 Agent 执行</option></select></label>
              <label className="space-y-1.5 text-sm"><span className="font-medium">调度编排器</span><select value={form.collection_orchestrator} onChange={(event) => setField('collection_orchestrator', event.target.value as typeof form.collection_orchestrator)} className="h-9 w-full rounded-lg border bg-background px-3"><option value="admin">OpenCLI 内置</option><option value="iii">III Engine</option></select></label>
              <label className="space-y-1.5 text-sm"><span className="font-medium">最大并发任务</span><Input type="number" min={1} max={64} value={form.local_max_concurrent_pipelines} onChange={(event) => setField('local_max_concurrent_pipelines', Number(event.target.value))} /></label>
              <label className="space-y-1.5 text-sm"><span className="font-medium">OpenCLI 超时（秒）</span><Input type="number" min={1} max={3600} value={form.opencli_timeout} onChange={(event) => setField('opencli_timeout', Number(event.target.value))} /></label>
              <label className="space-y-1.5 text-sm sm:col-span-2"><span className="font-medium">默认时区</span><Input value={form.default_timezone} onChange={(event) => setField('default_timezone', event.target.value)} placeholder="Asia/Shanghai" /></label>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>浏览器与 Agent</CardTitle><CardDescription>管理本地 Chrome、远程节点与 Fleet 网络方式。</CardDescription></CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5 text-sm sm:col-span-2"><span className="font-medium">默认 CDP 地址</span><Input value={form.opencli_cdp_endpoint} onChange={(event) => setField('opencli_cdp_endpoint', event.target.value)} /></label>
              <label className="space-y-1.5 text-sm sm:col-span-2"><span className="font-medium">Agent Pool 地址（逗号分隔）</span><Input value={form.agent_pool_endpoints.join(',')} onChange={(event) => setField('agent_pool_endpoints', event.target.value.split(',').map((item) => item.trim()).filter(Boolean))} placeholder="http://agent-1:19222" /></label>
              <label className="space-y-1.5 text-sm"><span className="font-medium">网络方式</span><select value={form.fleet_network_provider} onChange={(event) => setField('fleet_network_provider', event.target.value as typeof form.fleet_network_provider)} className="h-9 w-full rounded-lg border bg-background px-3"><option value="lan">LAN</option><option value="netbird">NetBird</option><option value="wireguard">WireGuard</option><option value="ssh">SSH Tunnel</option><option value="custom">Custom</option></select></label>
              <label className="space-y-1.5 text-sm"><span className="font-medium">NetBird 模式</span><select value={form.netbird_mode} onChange={(event) => setField('netbird_mode', event.target.value as typeof form.netbird_mode)} className="h-9 w-full rounded-lg border bg-background px-3"><option value="off">关闭</option><option value="host">宿主机</option><option value="docker">Docker</option></select></label>
              <label className="space-y-1.5 text-sm sm:col-span-2"><span className="font-medium">对外访问地址</span><Input value={form.public_url} onChange={(event) => setField('public_url', event.target.value)} placeholder="http://192.168.1.10:8031" /></label>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>AI 与人机协作</CardTitle><CardDescription>限制模型调用资源，并设置 Agent 控制策略。</CardDescription></CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5 text-sm"><span className="font-medium">模型请求超时（秒）</span><Input type="number" min={1} max={3600} value={form.llm_request_timeout_seconds} onChange={(event) => setField('llm_request_timeout_seconds', Number(event.target.value))} /></label>
              <label className="space-y-1.5 text-sm"><span className="font-medium">模型并发数</span><Input type="number" min={1} max={64} value={form.llm_max_concurrency} onChange={(event) => setField('llm_max_concurrency', Number(event.target.value))} /></label>
              <label className="space-y-1.5 text-sm"><span className="font-medium">控制策略</span><select value={form.control_mode} onChange={(event) => setField('control_mode', event.target.value as typeof form.control_mode)} className="h-9 w-full rounded-lg border bg-background px-3"><option value="advisory">建议模式</option><option value="automatic">自动模式</option></select></label>
              <label className="flex items-center gap-3 rounded-lg border px-3 py-2 text-sm"><input type="checkbox" checked={form.control_kill_switch} onChange={(event) => setField('control_kill_switch', event.target.checked)} />全局暂停自动执行</label>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>集成与密钥状态</CardTitle><CardDescription>只显示配置状态，不在浏览器中暴露实际密钥。</CardDescription></CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between rounded-lg border px-3 py-2"><span>API / Fleet 访问令牌</span><StatusBadge configured={config.data.api_auth_configured} /></div>
              <div className="flex items-center justify-between rounded-lg border px-3 py-2"><span>凭证加密密钥</span><StatusBadge configured={config.data.credential_encryption_configured} /></div>
              <div className="flex items-center justify-between rounded-lg border px-3 py-2"><span>OIDC 组织登录</span><StatusBadge configured={config.data.oidc_configured} /></div>
              <div className="flex items-center justify-between rounded-lg border px-3 py-2"><span>SMTP 通知</span><StatusBadge configured={config.data.smtp_configured} /></div>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader><CardTitle>系统模块</CardTitle><CardDescription>从这里进入各个系统级管理区域，不再把配置散落在不同入口。</CardDescription></CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[
              ['/operations-agents', '自动化与智能体', '安排任务、选择 Agent 和查看活动'],
              ['/nodes', '执行资源', '管理浏览器节点与远程 Agent'],
              ['/providers', '模型与连接', '配置模型供应商和运行时连接'],
              ['/notifications', '通知与交付', '配置消息渠道和通知规则'],
              ['/control/actions', '控制与审计', '查看系统建议、执行记录和控制状态'],
              ['/inbox', '任务与日志', '处理失败任务、待确认操作和通知'],
            ].map(([href, title, description]) => (
              <Link key={href} href={href} className="rounded-lg border p-3 transition-colors hover:bg-muted/50">
                <span className="block text-sm font-medium">{title}</span>
                <span className="mt-1 block text-xs leading-5 text-muted-foreground">{description}</span>
              </Link>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>管理员账户</CardTitle><CardDescription>系统级设置的一部分：在这里修改本地管理员密码。</CardDescription></CardHeader>
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
