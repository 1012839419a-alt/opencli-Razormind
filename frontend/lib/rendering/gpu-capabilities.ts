export type GpuRendererBackend = 'pending' | 'webgl2' | 'fallback'

export type GpuCapabilities = {
  webgl2: boolean
  webgpuApiPresent: boolean
}

const UNSUPPORTED_CAPABILITIES: GpuCapabilities = {
  webgl2: false,
  webgpuApiPresent: false,
}

let cachedCapabilities: GpuCapabilities | null = null

/**
 * Performs an SSR-safe capability probe. This describes what the browser can
 * create, never the backend currently used by a product surface.
 */
export function probeGpuCapabilities(): GpuCapabilities {
  if (
    typeof window === 'undefined'
    || typeof document === 'undefined'
    || typeof navigator === 'undefined'
  ) {
    return UNSUPPORTED_CAPABILITIES
  }
  if (cachedCapabilities) return cachedCapabilities

  const webgpuApiPresent = 'gpu' in navigator
  let webgl2 = false
  try {
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('webgl2')
    webgl2 = Boolean(context && !context.isContextLost())
  } catch {
    webgl2 = false
  }

  cachedCapabilities = { webgl2, webgpuApiPresent }
  return cachedCapabilities
}

export function invalidateGpuCapabilitiesAfterContextLoss() {
  cachedCapabilities = null
}
