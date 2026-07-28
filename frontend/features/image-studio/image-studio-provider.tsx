'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

import {
  EMPTY_CANVAS_RECIPE,
  type CanvasDocument,
  type CanvasHostBridge,
  type CanvasRecipe,
  type ImageGenerationJob,
  type ImageModel,
  type MediaAsset,
} from './canvas-host-bridge'

type ImageStudioContextValue = {
  document: CanvasDocument | null
  recipe: CanvasRecipe
  assets: MediaAsset[]
  models: ImageModel[]
  job: ImageGenerationJob | null
  loading: boolean
  saving: boolean
  dirty: boolean
  error: string | null
  updateRecipe: (update: (current: CanvasRecipe) => CanvasRecipe) => void
  save: () => Promise<void>
  importAsset: (file: File) => Promise<MediaAsset>
  generate: () => Promise<void>
  cancel: () => Promise<void>
  refreshAssets: () => Promise<void>
}

const ImageStudioContext = createContext<ImageStudioContextValue | null>(null)

export function ImageStudioProvider({ bridge, children }: { bridge: CanvasHostBridge; children: React.ReactNode }) {
  const [document, setDocument] = useState<CanvasDocument | null>(null)
  const [recipe, setRecipe] = useState<CanvasRecipe>(EMPTY_CANVAS_RECIPE)
  const [assets, setAssets] = useState<MediaAsset[]>([])
  const [models, setModels] = useState<ImageModel[]>([])
  const [job, setJob] = useState<ImageGenerationJob | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const unsubscribeRef = useRef<null | (() => void)>(null)

  const refreshAssets = useCallback(async () => {
    setAssets(await bridge.listAssets())
  }, [bridge])

  useEffect(() => {
    let active = true
    void Promise.all([bridge.loadDocument(), bridge.listAssets(), bridge.getModelCatalog()])
      .then(([loadedDocument, loadedAssets, loadedModels]) => {
        if (!active) return
        setDocument(loadedDocument)
        setRecipe(loadedDocument.document)
        setAssets(loadedAssets)
        setModels(loadedModels)
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : '图像工作台加载失败')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
      unsubscribeRef.current?.()
      unsubscribeRef.current = null
      bridge.dispose?.()
    }
  }, [bridge])

  const updateRecipe = useCallback((update: (current: CanvasRecipe) => CanvasRecipe) => {
    setRecipe((current) => update(current))
    setDirty(true)
  }, [])

  const save = useCallback(async () => {
    if (!document || !dirty) return
    setSaving(true)
    setError(null)
    try {
      const saved = await bridge.saveDocument(recipe, document.revision)
      setDocument(saved)
      setRecipe(saved.document)
      setDirty(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存失败')
      throw cause
    } finally {
      setSaving(false)
    }
  }, [bridge, dirty, document, recipe])

  const importAsset = useCallback(async (file: File) => {
    const asset = await bridge.importAsset(file)
    setAssets((current) => [asset, ...current.filter((item) => item.id !== asset.id)])
    return asset
  }, [bridge])

  const generate = useCallback(async () => {
    setError(null)
    if (dirty) await save()
    const snapshot = await bridge.createSnapshot()
    const idempotencyKey = globalThis.crypto?.randomUUID?.() ?? `${snapshot.id}-${Date.now()}`
    const createdJob = await bridge.enqueueGeneration({
      snapshotId: snapshot.id,
      prompt: recipe.prompt,
      negativePrompt: recipe.negativePrompt,
      idempotencyKey,
    })
    setJob(createdJob)
    unsubscribeRef.current?.()
    const unsubscribe = bridge.subscribeJobEvents(
      createdJob.id,
      (event) => {
        setJob(event.job)
        if (event.job.status === 'succeeded') void refreshAssets()
        if (['succeeded', 'blocked', 'failed', 'cancelled', 'timed_out'].includes(event.job.status)) {
          unsubscribeRef.current?.()
          unsubscribeRef.current = null
        }
      },
      async () => {
        try {
          setJob(await bridge.getJobStatus(createdJob.id))
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : '任务状态回查失败')
        }
      },
    )
    unsubscribeRef.current = unsubscribe
  }, [bridge, dirty, recipe.negativePrompt, recipe.prompt, refreshAssets, save])

  const cancel = useCallback(async () => {
    if (!job) return
    setJob(await bridge.cancelGeneration(job.id))
  }, [bridge, job])

  const value = useMemo<ImageStudioContextValue>(() => ({
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
    refreshAssets,
  }), [assets, cancel, dirty, document, error, generate, importAsset, job, loading, models, recipe, refreshAssets, save, saving, updateRecipe])

  return <ImageStudioContext.Provider value={value}>{children}</ImageStudioContext.Provider>
}

export function useImageStudio(): ImageStudioContextValue {
  const context = useContext(ImageStudioContext)
  if (!context) throw new Error('useImageStudio must be used within ImageStudioProvider')
  return context
}
