'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useAuth } from '@/components/auth/auth-provider'
import { BACKEND_HINT, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useSystemConfig, useUpdateSystemConfig } from '@/lib/api/hooks'

export default function SystemSettingsPage() {
  const config = useSystemConfig()
  const updateConfig = useUpdateSystemConfig()
  const { changePassword } = useAuth()
  const [collectionMode, setCollectionMode] = useState<'local' | 'agent'>('local')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [savingPassword, setSavingPassword] = useState(false)

  useEffect(() => {
    if (config.data) setCollectionMode(config.data.collection_mode)
  }, [config.data])

  async function saveCollectionMode() {
    try {
      await updateConfig.mutateAsync({ collection_mode: collectionMode })
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
      description="管理整套 OpenCLI 部署、管理员账户与系统级配置。"
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>执行模式</CardTitle>
            <CardDescription>决定采集任务由当前服务执行，还是交给远程 Agent。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="block space-y-2 text-sm">
              <span className="font-medium">采集执行位置</span>
              <select
                value={collectionMode}
                onChange={(event) => setCollectionMode(event.target.value as 'local' | 'agent')}
                className="h-9 w-full rounded-lg border bg-background px-3"
              >
                <option value="local">本机执行</option>
                <option value="agent">远程 Agent 执行</option>
              </select>
            </label>
            <Button onClick={() => void saveCollectionMode()} disabled={updateConfig.isPending}>
              {updateConfig.isPending ? '保存中…' : '保存执行模式'}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>当前运行环境</CardTitle>
            <CardDescription>当前部署读取到的基础运行信息。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center justify-between rounded-lg border px-3 py-2">
              <span className="text-muted-foreground">任务执行器</span>
              <span className="font-medium">{config.data.task_executor}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border px-3 py-2">
              <span className="text-muted-foreground">镜像版本</span>
              <span className="font-mono text-xs">{config.data.image_tag}</span>
            </div>
            <p className="text-xs leading-5 text-muted-foreground">
              模型连接、浏览器节点和自动化分别在对应功能页管理。
            </p>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>管理员账户</CardTitle>
            <CardDescription>在这里修改本地管理员密码，不再单独跳转到账户设置页面。</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="max-w-xl space-y-5" onSubmit={savePassword}>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="current-password">当前密码</FieldLabel>
                  <Input
                    id="current-password"
                    type="password"
                    autoComplete="current-password"
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                    required
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="new-password">新密码</FieldLabel>
                  <Input
                    id="new-password"
                    type="password"
                    autoComplete="new-password"
                    minLength={6}
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    required
                  />
                  <FieldDescription>至少 6 个字符。</FieldDescription>
                </Field>
                <Field>
                  <FieldLabel htmlFor="confirm-password">确认新密码</FieldLabel>
                  <Input
                    id="confirm-password"
                    type="password"
                    autoComplete="new-password"
                    minLength={6}
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    required
                  />
                </Field>
              </FieldGroup>
              <Button type="submit" disabled={savingPassword}>
                {savingPassword ? '保存中…' : '保存密码'}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  )
}
