import { apiClient } from '@/lib/api/client'
import { getApiAuthHeaders } from '@/lib/api/auth-headers'

import {
  EMPTY_CANVAS_RECIPE,
  type CanvasAssetLayer,
  type CanvasDocument,
  type CanvasHostBridge,
  type CanvasRecipe,
  type CanvasSnapshot,
  type ImageGenerationEvent,
  type ImageGenerationJob,
  type ImageModel,
  type MediaAsset,
} from './canvas-host-bridge'

type ApiEnvelope<T> = { success: boolean; data: T; error?: string | null }

export type ImageStudioScope = {
  workspaceId: string
  projectId: string
  workflowId: string
  nodeId: string
  documentId?: string | null
  onDocumentResolved?: (documentId: string) => void
}

function segment(value: string): string {
  return encodeURIComponent(value)
}

function platformHeaders(accept: string): HeadersInit {
  return { Accept: accept, ...getApiAuthHeaders() }
}

export function createPlatformCanvasHostBridge(scope: ImageStudioScope): CanvasHostBridge {
  const base = `/workspaces/${segment(scope.workspaceId)}/projects/${segment(scope.projectId)}/image-studio`
  let documentId = scope.documentId ?? null
  let currentDocument: CanvasDocument | null = null
  let modelCatalog: ImageModel[] = []
  const assetObjectUrls = new Map<string, string>()

  const withObjectUrl = async (asset: MediaAsset): Promise<MediaAsset> => {
    const cached = assetObjectUrls.get(asset.id)
    if (cached) return { ...asset, contentUrl: cached }
    const response = await fetch(asset.contentUrl, { headers: platformHeaders(asset.mimeType) })
    if (!response.ok) throw new Error(`资产内容读取失败 (${response.status})`)
    const objectUrl = URL.createObjectURL(await response.blob())
    assetObjectUrls.set(asset.id, objectUrl)
    return { ...asset, contentUrl: objectUrl }
  }

  const requireDocumentId = () => {
    if (!documentId) throw new Error('Canvas 文档尚未初始化')
    return segment(documentId)
  }

  const getJobStatus = (jobId: string) => apiClient
    .get<ApiEnvelope<ImageGenerationJob>>(`${base}/jobs/${segment(jobId)}`)
    .then((response) => response.data.data)

  const pollJobUntilTerminal = async (
    jobId: string,
    startSequence: number,
    onEvent: (event: ImageGenerationEvent) => void,
    isStopped: () => boolean,
  ) => {
    const terminal = new Set(['succeeded', 'blocked', 'failed', 'cancelled', 'timed_out'])
    let sequence = startSequence
    while (!isStopped()) {
      await new Promise((resolve) => window.setTimeout(resolve, 1500))
      if (isStopped()) return
      const job = await getJobStatus(jobId)
      onEvent({ sequence: sequence++, type: 'status', job })
      if (terminal.has(job.status)) return
    }
  }

  return {
    async loadDocument() {
      if (documentId) {
        const loaded = await apiClient
          .get<ApiEnvelope<CanvasDocument>>(`${base}/documents/${segment(documentId)}`)
          .then((response) => response.data.data)
        scope.onDocumentResolved?.(loaded.id)
        currentDocument = loaded
        return loaded
      }

      const created = await apiClient
        .post<ApiEnvelope<CanvasDocument>>(`${base}/documents`, {
          workflowId: scope.workflowId,
          nodeId: scope.nodeId,
          document: { ...EMPTY_CANVAS_RECIPE, layers: [] },
        })
        .then((response) => response.data.data)
      documentId = created.id
      currentDocument = created
      scope.onDocumentResolved?.(created.id)
      return created
    },

    async saveDocument(document: CanvasRecipe, expectedRevision: number) {
      const saved = await apiClient
        .put<ApiEnvelope<CanvasDocument>>(`${base}/documents/${requireDocumentId()}`, {
          expectedRevision,
          document,
        })
        .then((response) => response.data.data)
      currentDocument = saved
      return saved
    },

    createSnapshot() {
      if (!currentDocument) throw new Error('Canvas 文档尚未加载')
      const recipe = currentDocument.document
      const selectedModel = modelCatalog.find((model) => model.key === recipe.modelKey)
      if (!selectedModel?.available) throw new Error('请选择当前可用的生成模型')
      const assetIds = recipe.layers
        .filter((layer): layer is CanvasAssetLayer => layer.type === 'asset')
        .map((layer) => layer.assetId)
      return apiClient
        .post<ApiEnvelope<CanvasSnapshot>>(`${base}/documents/${requireDocumentId()}/snapshots`, {
          expectedRevision: currentDocument.revision,
          executableGraph: { schemaVersion: 'opencli.image-generation.v1', recipe },
          modelFingerprint: selectedModel.fingerprint,
          seed: recipe.seed,
          loraRevisions: [],
          assetIds,
        })
        .then((response) => response.data.data)
    },

    async listAssets() {
      const assets = await apiClient
        .get<ApiEnvelope<MediaAsset[]>>(`${base}/media-assets`)
        .then((response) => response.data.data)
      return Promise.all(assets.map(withObjectUrl))
    },

    async importAsset(file: File) {
      const body = new FormData()
      body.set('file', file)
      const imported = await apiClient
        .post<ApiEnvelope<MediaAsset>>(`${base}/media-assets/import`, body, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((response) => response.data.data)
      return withObjectUrl(imported)
    },

    async getModelCatalog() {
      modelCatalog = await apiClient
        .get<ApiEnvelope<ImageModel[]>>(`${base}/models`)
        .then((response) => response.data.data)
      return modelCatalog
    },

    enqueueGeneration(input) {
      return apiClient
        .post<ApiEnvelope<ImageGenerationJob>>(`${base}/jobs`, {
          snapshotId: input.snapshotId,
          runId: input.snapshotId,
          nodeId: scope.nodeId,
          attempt: 1,
          idempotencyKey: input.idempotencyKey,
          mode: 'preview',
        })
        .then((response) => response.data.data)
    },

    cancelGeneration(jobId: string) {
      return apiClient
        .post<ApiEnvelope<ImageGenerationJob>>(`${base}/jobs/${segment(jobId)}/cancel`, {})
        .then((response) => response.data.data)
    },

    getJobStatus,

    subscribeJobEvents(jobId, onEvent, onError) {
      const controller = new AbortController()
      let stopped = false
      let sequence = 1
      let terminal = false

      void (async () => {
        try {
          const response = await fetch(`/api/v1${base}/jobs/${segment(jobId)}/events`, {
            headers: platformHeaders('text/event-stream'),
            signal: controller.signal,
          })
          if (!response.ok || !response.body) throw new Error(`任务事件流不可用 (${response.status})`)

          const reader = response.body.getReader()
          const decoder = new TextDecoder()
          let buffer = ''
          while (!stopped) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            const frames = buffer.split('\n\n')
            buffer = frames.pop() ?? ''
            for (const frame of frames) {
              const payload = frame
                .split('\n')
                .filter((line) => line.startsWith('data:'))
                .map((line) => line.slice(5).trimStart())
                .join('\n')
              if (payload) {
                const event = JSON.parse(payload) as ImageGenerationEvent
                sequence = Math.max(sequence, event.sequence + 1)
                terminal = ['succeeded', 'blocked', 'failed', 'cancelled', 'timed_out']
                  .includes(event.job.status)
                onEvent(event)
              }
            }
          }
          if (!stopped && !terminal) {
            await pollJobUntilTerminal(jobId, sequence, onEvent, () => stopped)
          }
        } catch (error) {
          if (!stopped && !(error instanceof DOMException && error.name === 'AbortError')) {
            onError?.(error instanceof Error ? error : new Error('任务事件流中断'))
          }
        }
      })()

      return () => {
        stopped = true
        controller.abort()
      }
    },

    dispose() {
      for (const objectUrl of assetObjectUrls.values()) URL.revokeObjectURL(objectUrl)
      assetObjectUrls.clear()
    },
  }
}
