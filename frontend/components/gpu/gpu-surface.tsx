'use client'

import {
  Component,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from 'react'

import {
  invalidateGpuCapabilitiesAfterContextLoss,
  probeGpuCapabilities,
  type GpuRendererBackend,
} from '@/lib/rendering/gpu-capabilities'

type GpuFallbackReason =
  | 'probing'
  | 'unavailable'
  | 'reduced-motion'
  | 'page-hidden'
  | 'context-lost'
  | 'renderer-error'

type GpuSurfaceState = {
  backend: GpuRendererBackend
  fallbackReason: GpuFallbackReason | null
  webgpuApiPresent: boolean
}

type GpuSurfaceProps = {
  children: ReactNode
  fallback: ReactNode
  surface: string
  className?: string
}

type RendererErrorBoundaryProps = {
  children: ReactNode
  onError: () => void
}

type RendererErrorBoundaryState = {
  failed: boolean
}

class RendererErrorBoundary extends Component<
  RendererErrorBoundaryProps,
  RendererErrorBoundaryState
> {
  state: RendererErrorBoundaryState = { failed: false }

  static getDerivedStateFromError(): RendererErrorBoundaryState {
    return { failed: true }
  }

  componentDidCatch() {
    this.props.onError()
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

export function GpuSurface({
  children,
  fallback,
  surface,
  className,
}: GpuSurfaceProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const retryTimerRef = useRef<number | null>(null)
  const refreshSurfaceRef = useRef<() => void>(() => {})
  const [state, setState] = useState<GpuSurfaceState>({
    backend: 'pending',
    fallbackReason: 'probing',
    webgpuApiPresent: false,
  })

  useEffect(() => {
    let disposed = false
    const motionQuery = typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-reduced-motion: reduce)')
      : null

    const updateSurface = () => {
      if (disposed) return

      const capabilities = probeGpuCapabilities()
      if (document.hidden) {
        setState({
          backend: 'fallback',
          fallbackReason: 'page-hidden',
          webgpuApiPresent: capabilities.webgpuApiPresent,
        })
        return
      }
      if (motionQuery?.matches) {
        setState({
          backend: 'fallback',
          fallbackReason: 'reduced-motion',
          webgpuApiPresent: capabilities.webgpuApiPresent,
        })
        return
      }
      if (!capabilities.webgl2) {
        setState({
          backend: 'fallback',
          fallbackReason: 'unavailable',
          webgpuApiPresent: capabilities.webgpuApiPresent,
        })
        return
      }
      setState({
        backend: 'webgl2',
        fallbackReason: null,
        webgpuApiPresent: capabilities.webgpuApiPresent,
      })
    }

    refreshSurfaceRef.current = updateSurface
    updateSurface()
    document.addEventListener('visibilitychange', updateSurface)
    motionQuery?.addEventListener('change', updateSurface)
    return () => {
      disposed = true
      refreshSurfaceRef.current = () => {}
      document.removeEventListener('visibilitychange', updateSurface)
      motionQuery?.removeEventListener('change', updateSurface)
    }
  }, [])

  useEffect(() => () => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current)
    }
  }, [])

  useEffect(() => {
    if (state.backend !== 'webgl2') return

    const host = hostRef.current
    if (!host) return

    const observedCanvases = new Set<HTMLCanvasElement>()
    const scheduleRecovery = () => {
      invalidateGpuCapabilitiesAfterContextLoss()
      if (retryTimerRef.current !== null) {
        window.clearTimeout(retryTimerRef.current)
      }
      retryTimerRef.current = window.setTimeout(() => {
        retryTimerRef.current = null
        refreshSurfaceRef.current()
      }, 250)
    }
    const handleContextLost = (event: Event) => {
      event.preventDefault()
      scheduleRecovery()
      setState((current) => current.backend === 'webgl2'
        ? {
            ...current,
            backend: 'fallback',
            fallbackReason: 'context-lost',
          }
        : current)
    }
    const observeCanvases = () => {
      observedCanvases.forEach((canvas) => {
        if (host.contains(canvas)) return
        canvas.removeEventListener('webglcontextlost', handleContextLost)
        observedCanvases.delete(canvas)
      })
      host.querySelectorAll('canvas').forEach((canvas) => {
        if (observedCanvases.has(canvas)) return
        canvas.addEventListener('webglcontextlost', handleContextLost)
        observedCanvases.add(canvas)
      })
    }

    observeCanvases()
    const observer = new MutationObserver(observeCanvases)
    observer.observe(host, { childList: true, subtree: true })
    return () => {
      observer.disconnect()
      observedCanvases.forEach((canvas) => {
        canvas.removeEventListener('webglcontextlost', handleContextLost)
      })
    }
  }, [state.backend])

  return (
    <div
      ref={hostRef}
      className={className}
      data-gpu-surface={surface}
      data-gpu-backend={state.backend}
      data-gpu-fallback-reason={state.fallbackReason ?? undefined}
      data-gpu-webgpu-api={state.webgpuApiPresent ? 'present' : 'absent'}
    >
      {state.backend === 'webgl2' ? (
        <RendererErrorBoundary
          onError={() => {
            setState((current) => ({
              ...current,
              backend: 'fallback',
              fallbackReason: 'renderer-error',
            }))
          }}
        >
          {children}
        </RendererErrorBoundary>
      ) : (
        <div className="h-full">
          {fallback}
        </div>
      )}
    </div>
  )
}
