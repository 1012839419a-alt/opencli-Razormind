'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useSystemConfig, useUpdateSystemConfig } from '@/lib/api/hooks'
import { BACKEND_HINT, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function SystemSettingsPage() {
  const config = useSystemConfig()
  const updateConfig = useUpdateSystemConfig()
  const [collectionMode, setCollectionMode] = useState<'local' | 'agent'>('local')

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

  if (config.isLoading) return <LoadingState />
  if (config.isError || !config.data) {
    return <ErrorState message={(config.error as Error)?.message} hint={BACKEND_HINT} />
  }

  return (
    <PageContainer
      eyebrow="SYSTEM"
      title="系统设置"
      description="管理整套 OpenCLI 部署的运行方式与系统级配置。"
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
              模型连接、浏览器节点、自动化与账户密码分别在对应设置页管理。
            </p>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  )
}
