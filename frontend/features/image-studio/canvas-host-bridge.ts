export type CanvasPoint = readonly [x: number, y: number, pressure: number]

export type CanvasStrokeLayer = {
  id: string
  type: 'stroke'
  name: string
  visible: boolean
  opacity: number
  blendMode: 'source-over' | 'multiply' | 'screen'
  tool: 'brush' | 'mask'
  color: string
  size: number
  points: CanvasPoint[]
}

export type CanvasAssetLayer = {
  id: string
  type: 'asset'
  name: string
  visible: boolean
  opacity: number
  blendMode: 'source-over' | 'multiply' | 'screen'
  assetId: string
  x: number
  y: number
  width: number
  height: number
}

export type CanvasLayer = CanvasStrokeLayer | CanvasAssetLayer

export type CanvasRecipe = {
  schemaVersion: 1
  width: number
  height: number
  background: string
  layers: CanvasLayer[]
  prompt: string
  negativePrompt: string
  modelKey: string | null
  seed: number
  steps: number
  cfgScale: number
}

export type CanvasDocument = {
  id: string
  workspaceId: string
  projectId: string
  workflowId: string
  nodeId: string
  revision: number
  document: CanvasRecipe
  createdAt: string
  updatedAt: string
}

export type CanvasSnapshot = {
  id: string
  documentId: string
  documentRevision: number
  canvasDocument: CanvasRecipe
  executableGraph: Record<string, unknown>
  modelFingerprint: string
  createdAt: string
}

export type MediaAsset = {
  id: string
  workspaceId: string
  projectId: string
  filename: string
  mimeType: string
  width: number | null
  height: number | null
  sha256: string
  contentUrl: string
  createdAt: string
}

export type ImageModel = {
  key: string
  name: string
  base: string | null
  type: string
  fingerprint: string
  available: boolean
}

export type ImageGenerationStatus =
  | 'queued'
  | 'submitted'
  | 'running'
  | 'ingesting'
  | 'succeeded'
  | 'blocked'
  | 'failed'
  | 'cancelled'
  | 'timed_out'

export type ImageGenerationJob = {
  id: string
  snapshotId: string
  status: ImageGenerationStatus
  progress?: number | null
  outputAssetIds: string[]
  errorCode: string | null
  errorDetail: string | null
  createdAt: string
  updatedAt: string
}

export type ImageGenerationEvent = {
  sequence: number
  type: 'status' | 'progress' | 'asset' | 'error' | 'heartbeat'
  job: ImageGenerationJob
}

export type CanvasHostBridge = {
  loadDocument(): Promise<CanvasDocument>
  saveDocument(document: CanvasRecipe, expectedRevision: number): Promise<CanvasDocument>
  createSnapshot(): Promise<CanvasSnapshot>
  listAssets(): Promise<MediaAsset[]>
  importAsset(file: File): Promise<MediaAsset>
  getModelCatalog(): Promise<ImageModel[]>
  enqueueGeneration(input: {
    snapshotId: string
    prompt: string
    negativePrompt: string
    idempotencyKey: string
  }): Promise<ImageGenerationJob>
  cancelGeneration(jobId: string): Promise<ImageGenerationJob>
  getJobStatus(jobId: string): Promise<ImageGenerationJob>
  subscribeJobEvents(
    jobId: string,
    onEvent: (event: ImageGenerationEvent) => void,
    onError?: (error: Error) => void,
  ): () => void
  dispose?(): void
}

export const EMPTY_CANVAS_RECIPE: CanvasRecipe = {
  schemaVersion: 1,
  width: 1024,
  height: 1024,
  background: '#ffffff',
  layers: [],
  prompt: '',
  negativePrompt: '',
  modelKey: null,
  seed: 0,
  steps: 30,
  cfgScale: 7.5,
}
