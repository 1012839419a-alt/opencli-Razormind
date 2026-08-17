'use client'

import { useEffect, useState } from 'react'
import { Loader2, Save, Settings2 } from 'lucide-react'
import { toast } from 'sonner'

import { useSystemConfig, useUpdateSystemConfig } from '@/lib/api/hooks'
import type { SystemConfig } from '@/lib/api/types'
import { BACKEND_HINT, ErrorState, LoadingState } from '@/components/shell/data-states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldTitle } from '@/components/ui/field'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const COLLECTION_MODE_LABEL: Record<SystemConfig['collection_mode'], string> = {
  local: '本地执行',
  agent: '远程 Agent',
}

const TASK_EXECUTOR_LABEL: Record<SystemConfig['task_executor'], string> = {
  local: 'Local（进程内 asyncio）',
  celery: 'Celery（分布式）',
}

export function SystemConfigCard() {
  const { data, isLoading, isError, error } = useSystemConfig()
  const updateMutation = useUpdateSystemConfig()
  const [collectionMode, setCollectionMode] = useState<SystemConfig['collection_mode'] | null>(null)

  // Seed local edit state once, on first load only — a background refetch
  // (e.g. window refocus) must not clobber an in-progress, unsaved selection.
  useEffect(() => {
    if (data && collectionMode === null) setCollectionMode(data.collection_mode)
  }, [data, collectionMode])

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Settings2 className="size-4" /> 系统配置
          </CardTitle>
        </CardHeader>
        <CardContent>
          <LoadingState rows={3} />
        </CardContent>
      </Card>
    )
  }

  if (isError || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Settings2 className="size-4" /> 系统配置
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
        </CardContent>
      </Card>
    )
  }

  const effectiveMode = collectionMode ?? data.collection_mode
  const dirty = effectiveMode !== data.collection_mode

  const handleSave = () => {
    if (!dirty) return
    updateMutation.mutate(
      { collection_mode: effectiveMode },
      {
        onSuccess: () => toast.success('系统配置已更新'),
        onError: (cause: Error) => toast.error(cause.message),
      },
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Settings2 className="size-4" /> 系统配置
        </CardTitle>
        <CardDescription>运行时可调整的采集策略；执行器与镜像版本由部署环境决定，此处只读。</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <FieldGroup className="gap-4">
          <Field>
            <FieldLabel htmlFor="collection-mode">采集模式</FieldLabel>
            <Select
              value={effectiveMode}
              onValueChange={(value) => setCollectionMode(value as SystemConfig['collection_mode'])}
            >
              <SelectTrigger id="collection-mode" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="local">{COLLECTION_MODE_LABEL.local}</SelectItem>
                <SelectItem value="agent">{COLLECTION_MODE_LABEL.agent}</SelectItem>
              </SelectContent>
            </Select>
            <FieldDescription>
              {effectiveMode === 'local'
                ? '采集任务直接在本服务器执行。'
                : '采集任务分发到已注册的远程 Edge Agent 节点，各节点在本地运行 opencli，结果通过 HTTP/WS 回传。'}
            </FieldDescription>
          </Field>

          <Field orientation="horizontal" className="items-center justify-between gap-3">
            <div className="min-w-0">
              <FieldTitle className="text-muted-foreground">任务执行器</FieldTitle>
              <FieldDescription>由部署环境变量决定，此页面不可修改。</FieldDescription>
            </div>
            <Badge variant="outline" className="shrink-0">
              {TASK_EXECUTOR_LABEL[data.task_executor] ?? data.task_executor}
            </Badge>
          </Field>

          <Field orientation="horizontal" className="items-center justify-between gap-3">
            <div className="min-w-0">
              <FieldTitle className="text-muted-foreground">镜像版本</FieldTitle>
              <FieldDescription>用于 Agent 安装脚本与节点向导；来自部署时的 IMAGE_TAG。</FieldDescription>
            </div>
            <Badge variant="outline" className="shrink-0 font-mono">
              {data.image_tag}
            </Badge>
          </Field>
        </FieldGroup>

        <Button
          size="sm"
          className="self-end gap-1.5"
          disabled={!dirty || updateMutation.isPending}
          onClick={handleSave}
        >
          {updateMutation.isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Save className="size-3.5" />
          )}
          保存更改
        </Button>
      </CardContent>
    </Card>
  )
}
