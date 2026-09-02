'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { CheckCircle2, CircleHelp, Loader2, RefreshCw, Route, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import {
  useModelDefaults,
  useProviderModels,
  usePutModelDefault,
  useSyncProviderModels,
  useUpdateProvider,
} from '@/lib/api/hooks'
import type { ModelDefaultCandidate, ModelProvider, ModelRole } from '@/lib/api/types'
import type { ProviderPreset } from '@/lib/provider-presets'
import { ProviderFormDialog } from '@/components/providers/provider-form-dialog'
import { ProviderPresetPicker } from '@/components/providers/provider-preset-picker'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const ROLES: ModelRole[] = ['chat', 'executor', 'enrichment']

function sameCandidate(a?: ModelDefaultCandidate, b?: ModelDefaultCandidate) {
  return a?.provider_id === b?.provider_id && a?.model_id === b?.model_id
}

function UsageVisibilityCard({ providers }: { providers: ModelProvider[] }) {
  const enabled = providers.filter((provider) => provider.enabled).length

  return (
    <Card className="border-dashed">
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <CircleHelp className="size-4 text-muted-foreground" />
            用量与额度
          </CardTitle>
          <CardDescription>不把运行时长误报成额度，只有供应商返回 usage 数据时才展示数字。</CardDescription>
        </div>
        <Badge variant="outline">诚实状态</Badge>
      </CardHeader>
      <CardContent className="grid gap-2 text-sm sm:grid-cols-3">
        <div className="rounded-lg border bg-muted/20 p-3">
          <div className="text-xs text-muted-foreground">本地 Claude Code</div>
          <div className="mt-1 font-medium">额度不可读取</div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">CLI 没有稳定的 5 小时额度查询接口。</p>
        </div>
        <div className="rounded-lg border bg-muted/20 p-3">
          <div className="text-xs text-muted-foreground">已启用 API</div>
          <div className="mt-1 font-mono text-lg">{enabled}</div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">当前没有接入 provider usage endpoint。</p>
        </div>
        <div className="rounded-lg border border-primary/20 bg-primary/[0.04] p-3">
          <div className="text-xs text-muted-foreground">执行策略</div>
          <div className="mt-1 font-medium text-primary">允许深度执行</div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">任务按完成度和超时策略结束，不因猜测额度提前截断。</p>
        </div>
      </CardContent>
    </Card>
  )
}

export function PrimaryModelCard({ providers }: { providers: ModelProvider[] }) {
  const { data: defaultsData, isLoading: defaultsLoading } = useModelDefaults()
  const defaultMap = useMemo(
    () => new Map((defaultsData?.data ?? []).map((item) => [item.role, item.candidates])),
    [defaultsData?.data],
  )
  const currentPrimary =
    defaultMap.get('chat')?.[0] ??
    defaultMap.get('executor')?.[0] ??
    defaultMap.get('enrichment')?.[0]

  const configuredPrimaries = ROLES.map((role) => defaultMap.get(role)?.[0]).filter(Boolean)
  const hasAdvancedRouting =
    configuredPrimaries.length > 1 &&
    configuredPrimaries.some((candidate) => !sameCandidate(candidate, configuredPrimaries[0]))

  const [providerId, setProviderId] = useState('')
  const [modelId, setModelId] = useState('')
  const [selectedPresetKey, setSelectedPresetKey] = useState<string | null>(null)
  const [providerDialogOpen, setProviderDialogOpen] = useState(false)
  const providerModels = useProviderModels(providerId || null)
  const syncModels = useSyncProviderModels()
  const putDefault = usePutModelDefault()
  const updateProvider = useUpdateProvider()

  const enabledProviders = providers.filter((provider) => provider.enabled)
  const selectedProvider = providers.find((provider) => provider.id === providerId)
  const discoveredModels = (providerModels.data?.data ?? []).filter((model) => model.enabled)
  const modelOptions = useMemo(() => {
    const ids = discoveredModels.map((model) => model.model_id)
    if (modelId && !ids.includes(modelId)) ids.unshift(modelId)
    return ids
  }, [discoveredModels, modelId])

  useEffect(() => {
    if (providerId || providers.length === 0) return
    const initialProviderId =
      currentPrimary?.provider_id ??
      enabledProviders[0]?.id ??
      providers[0]?.id ??
      ''
    setProviderId(initialProviderId)
  }, [currentPrimary?.provider_id, enabledProviders, providerId, providers])

  useEffect(() => {
    if (!providerId || modelId) return
    const configuredModel =
      currentPrimary?.provider_id === providerId ? currentPrimary.model_id : undefined
    const nextModel =
      configuredModel ??
      selectedProvider?.default_model ??
      discoveredModels[0]?.model_id ??
      ''
    setModelId(nextModel)
  }, [
    currentPrimary?.model_id,
    currentPrimary?.provider_id,
    discoveredModels,
    modelId,
    providerId,
    selectedProvider?.default_model,
  ])

  const handleSync = async () => {
    if (!providerId) return
    try {
      const result = await syncModels.mutateAsync(providerId)
      const total = result.added + result.updated
      toast.success(total > 0 ? `已获取 ${total} 个模型` : '模型目录已是最新')
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const handleSave = async () => {
    if (!providerId || !modelId) return
    const candidate = { provider_id: providerId, model_id: modelId }
    try {
      await updateProvider.mutateAsync({ id: providerId, data: { default_model: modelId } })
      for (const role of ROLES) {
        await putDefault.mutateAsync({ role, candidates: [candidate] })
      }
      toast.success('默认模型已应用')
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const saving = putDefault.isPending || updateProvider.isPending
  const handlePresetSelect = (preset: ProviderPreset) => {
    setSelectedPresetKey(preset.key)
    setProviderDialogOpen(true)
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="overflow-hidden">
        <CardHeader className="border-b bg-muted/20">
          <CardTitle className="text-base">选择模型供应商</CardTitle>
          <CardDescription>
            Coding Plan 使用套餐专属 Key；官方 API 使用普通按量 Key。请选择与你现有密钥对应的服务。
          </CardDescription>
        </CardHeader>
        <CardContent className="p-4">
          <ProviderPresetPicker selectedKey={selectedPresetKey} onSelect={handlePresetSelect} />
        </CardContent>
      </Card>

      {providers.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <Card className="overflow-hidden">
        <CardHeader className="border-b bg-muted/20">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Sparkles className="size-4 text-primary" />
                默认模型
              </CardTitle>
              <CardDescription className="mt-1">
                新手只需设置一次。对话、执行和内容处理默认使用同一个模型。
              </CardDescription>
            </div>
            {currentPrimary ? (
              <Badge variant="secondary" className="gap-1">
                <CheckCircle2 className="size-3" />
                已配置
              </Badge>
            ) : (
              <Badge variant="outline">待配置</Badge>
            )}
          </div>
        </CardHeader>

        <CardContent className="flex flex-col gap-5 p-5">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              供应商
              <Select
                value={providerId}
                onValueChange={(value) => {
                  setProviderId(value as string)
                  setModelId('')
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>
                    {() => selectedProvider?.name ?? '选择供应商'}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {providers.map((provider) => (
                    <SelectItem key={provider.id} value={provider.id} disabled={!provider.enabled}>
                      {provider.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>

            <label className="flex flex-col gap-2 text-sm font-medium">
              模型
              <div className="flex gap-2">
                <Select
                  value={modelId}
                  onValueChange={(value) => setModelId(value as string)}
                  disabled={providerModels.isLoading || modelOptions.length === 0}
                >
                  <SelectTrigger className="min-w-0 flex-1">
                    <SelectValue
                      placeholder={
                        providerModels.isLoading ? '正在读取模型…' : '先自动获取模型'
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {modelOptions.map((id) => (
                      <SelectItem key={id} value={id}>
                        {id}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  variant="outline"
                  disabled={!providerId || syncModels.isPending}
                  onClick={handleSync}
                  className="shrink-0 gap-1.5"
                >
                  {syncModels.isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <RefreshCw className="size-4" />
                  )}
                  自动获取
                </Button>
              </div>
              {providerId && !providerModels.isLoading ? (
                <span className="text-xs font-normal text-muted-foreground">
                  {modelOptions.length > 0
                    ? `已发现 ${modelOptions.length} 个模型`
                    : '尚未发现模型'}
                </span>
              ) : null}
            </label>
          </div>

          {providerModels.isError ? (
            <p className="text-sm text-destructive">
              {(providerModels.error as Error)?.message ?? '模型获取失败'}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
            <p className="text-xs text-muted-foreground">
              {selectedProvider?.base_url || '使用供应商默认地址'}
            </p>
            <Button
              disabled={defaultsLoading || !providerId || !modelId || saving}
              onClick={handleSave}
              className="min-w-28"
            >
              {saving ? '应用中…' : '设为默认'}
            </Button>
          </div>
        </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Route className="size-4" />
                高级路由
              </CardTitle>
              <CardDescription>
                {hasAdvancedRouting
                  ? '当前不同场景使用了独立模型和候选顺序。'
                  : '需要冗余时，再为不同场景配置候选模型。'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Link
                href="/providers/routing"
                className={buttonVariants({ variant: 'outline', className: 'w-full' })}
              >
                管理模型路由
              </Link>
            </CardContent>
          </Card>
        </div>
      ) : (
        <p className="rounded-xl border border-dashed px-4 py-5 text-center text-sm text-muted-foreground">
          选择上方任一供应商，完成连接后即可设置默认模型。
        </p>
      )}

      <UsageVisibilityCard providers={providers} />

      <ProviderFormDialog
        mode="create"
        triggerLabel="添加供应商"
        initialPresetKey={selectedPresetKey}
        controlledOpen={providerDialogOpen}
        onControlledOpenChange={setProviderDialogOpen}
        hideTrigger
      />
    </div>
  )
}
