'use client'

import dynamic from 'next/dynamic'
import { useRouter, useSearchParams } from 'next/navigation'
import { useMemo, useState } from 'react'

import { useAuth } from '@/components/auth/auth-provider'
import { createPlatformCanvasHostBridge } from '@/features/image-studio/platform-canvas-host-bridge'

const ImageStudioHost = dynamic(() => import('@/features/image-studio/image-studio-host'), {
  ssr: false,
  loading: () => <div className="fixed inset-0 z-50 grid place-items-center bg-background text-sm text-muted-foreground">正在加载图像工作台…</div>,
})

function required(search: URLSearchParams, name: string): string {
  const value = search.get(name)?.trim()
  if (!value) throw new Error(`缺少 ${name}`)
  return value
}

export default function ImageStudioPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { identity } = useAuth()
  const [resolvedDocumentId, setResolvedDocumentId] = useState<string | null>(null)
  const query = searchParams.toString()
  const mode = searchParams.get('mode') === 'gallery' ? 'asset-picker' : 'authoring'
  const bridge = useMemo(() => {
    const search = new URLSearchParams(query)
    return createPlatformCanvasHostBridge({
      workspaceId: required(search, 'workspace'),
      projectId: required(search, 'project'),
      workflowId: required(search, 'workflow'),
      nodeId: required(search, 'node'),
      documentId: search.get('document'),
      onDocumentResolved: setResolvedDocumentId,
    })
  }, [query])

  const exit = (selectedAssetIds: string[] = []) => {
    const search = new URLSearchParams(query)
    const returnTo = search.get('returnTo')
    const [returnPath, returnQuery = ''] = returnTo?.startsWith('/studio/workflow')
      ? returnTo.split('?')
      : ['/studio/workflow', '']
    const workflowSearch = new URLSearchParams(returnQuery)
    workflowSearch.set('workspace', required(search, 'workspace'))
    workflowSearch.set('project', required(search, 'project'))
    workflowSearch.set('workflow', required(search, 'workflow'))
    workflowSearch.set('imageNode', required(search, 'node'))
    if (resolvedDocumentId) workflowSearch.set('imageDocument', resolvedDocumentId)
    if (selectedAssetIds.length) workflowSearch.set('imageAssets', selectedAssetIds.join(','))
    router.replace(`${returnPath}?${workflowSearch}`)
  }

  return <ImageStudioHost bridge={bridge} isPlatformAdmin={Boolean(identity?.is_platform_admin)} mode={mode} onExit={exit} />
}
