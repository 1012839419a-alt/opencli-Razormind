'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, ImagePlus, Layers3, Loader2, Play, Save, Square } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'

import type { CanvasAssetLayer, CanvasHostBridge, MediaAsset } from './canvas-host-bridge'
import { ImageStudioCanvas } from './image-studio-canvas'
import { ImageStudioProvider, useImageStudio } from './image-studio-provider'

type ImageStudioHostProps = {
  bridge: CanvasHostBridge
  isPlatformAdmin: boolean
  mode?: 'authoring' | 'asset-picker'
  onExit: (selectedAssetIds?: string[]) => void
}

const TERMINAL_JOB_STATES = new Set(['succeeded', 'blocked', 'failed', 'cancelled', 'timed_out'])

function assetLayer(asset: MediaAsset): CanvasAssetLayer {
  return {
    id: globalThis.crypto?.randomUUID?.() ?? `asset-${asset.id}-${Date.now()}`,
    type: 'asset',
    name: asset.filename,
    visible: true,
    opacity: 1,
    blendMode: 'source-over',
    assetId: asset.id,
    x: 0,
    y: 0,
    width: asset.width ?? 512,
    height: asset.height ?? 512,
  }
}

function ImageStudioWorkspace({ isPlatformAdmin, mode = 'authoring', onExit }: Omit<ImageStudioHostProps, 'bridge'>) {
  const {
    document,
    recipe,
    assets,
    models,
    job,
    loading,
    saving,
    dirty,
    error,
    updateRecipe,
    save,
    importAsset,
    generate,
    cancel,
  } = useImageStudio()
  const fileRef = useRef<HTMLInputElement | null>(null)
  const [tab, setTab] = useState(mode === 'asset-picker' ? 'gallery' : 'canvas')
  const [selectedAssetIds, setSelectedAssetIds] = useState<Set<string>>(() => new Set())
  const running = Boolean(job && !TERMINAL_JOB_STATES.has(job.status))

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        void save()
      }
      if (event.key === 'Escape') onExit([])
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onExit, save])

  const orderedTabs = useMemo(() => [
    { id: 'canvas', label: 'Canvas' },
    { id: 'gallery', label: '图库' },
    { id: 'graph', label: '生成图' },
    ...(isPlatformAdmin ? [{ id: 'models', label: '模型' }] : []),
  ], [isPlatformAdmin])

  const addAsset = (asset: MediaAsset) => {
    updateRecipe((current) => ({ ...current, layers: [...current.layers, assetLayer(asset)] }))
    setTab('canvas')
  }

  if (loading) {
    return <div className="fixed inset-0 z-50 grid place-items-center bg-background"><Loader2 className="size-6 animate-spin" /></div>
  }

  return (
    <main className="fixed inset-0 z-50 flex min-h-0 flex-col bg-background text-foreground" data-image-studio-document={document?.id}>
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-3">
        <Button variant="ghost" size="icon" aria-label="返回工作流" onClick={() => onExit([])}><ArrowLeft /></Button>
        <div className="min-w-0">
          <div className="flex items-center gap-2"><h1 className="truncate text-sm font-semibold">图像创作</h1><Badge variant="outline">第一方 Canvas</Badge></div>
          <p className="truncate text-xs text-muted-foreground">{dirty ? '有未保存修改' : `Revision ${document?.revision ?? 0}`}</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {error ? <span className="max-w-72 truncate text-xs text-destructive" title={error}>{error}</span> : null}
          {mode === 'asset-picker' ? (
            <Button disabled={selectedAssetIds.size === 0} onClick={() => onExit([...selectedAssetIds])}>使用所选 ({selectedAssetIds.size})</Button>
          ) : <><Button variant="outline" disabled={!dirty || saving} onClick={() => void save()}>
            {saving ? <Loader2 className="animate-spin" /> : <Save />}保存
          </Button>
          {running ? (
            <Button variant="destructive" onClick={() => void cancel()}><Square />取消生成</Button>
          ) : (
            <Button disabled={!recipe.prompt.trim()} onClick={() => void generate()}><Play />生成</Button>
          )}
          </>}
        </div>
      </header>

      <Tabs value={tab} onValueChange={(value) => setTab(String(value))} className="min-h-0 flex-1 gap-0">
        <TabsList variant="line" className="h-10 w-full shrink-0 justify-start border-b border-border px-4">
          {orderedTabs.map((item) => <TabsTrigger key={item.id} value={item.id}>{item.label}</TabsTrigger>)}
        </TabsList>

        <TabsContent value="canvas" className="min-h-0 data-[hidden]:hidden">
          <div className="flex h-full min-h-0">
            <ImageStudioCanvas recipe={recipe} assets={assets} onChange={(next) => updateRecipe(() => next)} />
            <aside className="w-80 shrink-0 overflow-y-auto border-l border-border p-4">
              <div className="mb-5 flex items-center gap-2 text-sm font-medium"><Layers3 className="size-4" />生成参数</div>
              <label className="mb-4 block text-xs text-muted-foreground">提示词
                <Textarea className="mt-1 min-h-28" value={recipe.prompt} onChange={(event) => updateRecipe((current) => ({ ...current, prompt: event.target.value }))} />
              </label>
              <label className="mb-4 block text-xs text-muted-foreground">反向提示词
                <Textarea className="mt-1 min-h-20" value={recipe.negativePrompt} onChange={(event) => updateRecipe((current) => ({ ...current, negativePrompt: event.target.value }))} />
              </label>
              <label className="mb-4 block text-xs text-muted-foreground">模型
                <select className="mt-1 h-8 w-full rounded-lg border border-input bg-background px-2 text-sm" value={recipe.modelKey ?? ''} onChange={(event) => updateRecipe((current) => ({ ...current, modelKey: event.target.value || null }))}>
                  <option value="">选择模型</option>
                  {models.filter((model) => model.available).map((model) => <option key={model.key} value={model.key}>{model.name}</option>)}
                </select>
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs text-muted-foreground">Seed<Input className="mt-1" type="number" value={recipe.seed} onChange={(event) => updateRecipe((current) => ({ ...current, seed: Number(event.target.value) }))} /></label>
                <label className="text-xs text-muted-foreground">Steps<Input className="mt-1" type="number" min={1} max={150} value={recipe.steps} onChange={(event) => updateRecipe((current) => ({ ...current, steps: Number(event.target.value) }))} /></label>
              </div>
            </aside>
          </div>
        </TabsContent>

        <TabsContent value="gallery" className="overflow-y-auto p-5 data-[hidden]:hidden">
          <div className="mb-4 flex items-center justify-between">
            <div><h2 className="text-base font-semibold">工作区图库</h2><p className="text-xs text-muted-foreground">所有素材先进入 OpenCLI 资产库，再用于 Canvas。</p></div>
            <input ref={fileRef} className="hidden" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void importAsset(file).then(addAsset)
              event.currentTarget.value = ''
            }} />
            <Button variant="outline" onClick={() => fileRef.current?.click()}><ImagePlus />导入素材</Button>
          </div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
            {assets.map((asset) => (
              <button
                key={asset.id}
                className={`overflow-hidden rounded-xl border bg-card text-left transition-colors hover:border-foreground/40 ${selectedAssetIds.has(asset.id) ? 'border-foreground ring-2 ring-foreground/20' : 'border-border'}`}
                onClick={() => {
                  if (mode !== 'asset-picker') return
                  setSelectedAssetIds((current) => {
                    const next = new Set(current)
                    if (next.has(asset.id)) next.delete(asset.id)
                    else next.add(asset.id)
                    return next
                  })
                }}
                onDoubleClick={() => { if (mode === 'authoring') addAsset(asset) }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={asset.contentUrl} alt={asset.filename} className="aspect-square w-full object-cover" />
                <span className="block truncate p-2 text-xs">{asset.filename}</span>
              </button>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="graph" className="overflow-y-auto p-5 data-[hidden]:hidden">
          <h2 className="mb-3 text-base font-semibold">生成图</h2>
          <div className="rounded-xl border border-border bg-card p-4">
            {job ? (
              <div className="space-y-2 text-sm"><div className="flex items-center justify-between"><span>任务 {job.id}</span><Badge>{job.status}</Badge></div><div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full bg-foreground transition-[width]" style={{ width: `${Math.round((job.progress ?? 0) * 100)}%` }} /></div>{job.errorDetail ? <p className="text-destructive">{job.errorDetail}</p> : null}</div>
            ) : <p className="text-sm text-muted-foreground">尚无生成任务。保存配方并提交后，队列状态会显示在这里。</p>}
          </div>
        </TabsContent>

        {isPlatformAdmin ? <TabsContent value="models" className="overflow-y-auto p-5 data-[hidden]:hidden"><h2 className="mb-3 text-base font-semibold">模型</h2><div className="divide-y divide-border rounded-xl border border-border">{models.map((model) => <div key={model.key} className="flex items-center justify-between p-3"><div><p className="text-sm font-medium">{model.name}</p><p className="font-mono text-xs text-muted-foreground">{model.fingerprint}</p></div><Badge variant={model.available ? 'default' : 'outline'}>{model.available ? '可用' : '缺失'}</Badge></div>)}</div></TabsContent> : null}
      </Tabs>
    </main>
  )
}

export default function ImageStudioHost(props: ImageStudioHostProps) {
  return <ImageStudioProvider bridge={props.bridge}><ImageStudioWorkspace isPlatformAdmin={props.isPlatformAdmin} mode={props.mode} onExit={props.onExit} /></ImageStudioProvider>
}
