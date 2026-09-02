export type ApiHealthSnapshot = Readonly<{
  status: string
  instance_id?: string
}>

export type ApiRestartRecoveryStatus = 'recovered' | 'timeout' | 'cancelled'

export type ApiRestartRecoveryOutcome = Readonly<{
  status: ApiRestartRecoveryStatus
  outageObserved: boolean
}>

export type ApiRestartRecoveryOptions = Readonly<{
  baselineInstanceId?: string
  initialOutageObserved?: boolean
  probe: (signal: AbortSignal) => Promise<ApiHealthSnapshot>
  refreshActiveData: () => Promise<unknown>
  signal: AbortSignal
  intervalMs?: number
  maxAttempts?: number
  delay?: (milliseconds: number, signal: AbortSignal) => Promise<void>
}>

export type ApiRestartRecoveryRun = Readonly<{
  token: symbol
  controller: AbortController
}>

export type ApiRestartRecoveryRunCoordinator = Readonly<{
  begin: () => ApiRestartRecoveryRun
  cancel: (run: ApiRestartRecoveryRun) => void
  finish: (run: ApiRestartRecoveryRun) => void
  isCurrent: (run: ApiRestartRecoveryRun) => boolean
}>

function normalizedInstanceId(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function abortableDelay(milliseconds: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted || milliseconds <= 0) return Promise.resolve()
  return new Promise<void>((resolve) => {
    const timeout = window.setTimeout(done, milliseconds)
    signal.addEventListener('abort', done, { once: true })

    function done() {
      window.clearTimeout(timeout)
      signal.removeEventListener('abort', done)
      resolve()
    }
  })
}

export function getApiInstanceId(value: unknown): string | undefined {
  if (!value || typeof value !== 'object' || !('instance_id' in value)) return undefined
  return normalizedInstanceId((value as { instance_id?: unknown }).instance_id)
}

export function createApiRestartRecoveryRunCoordinator(): ApiRestartRecoveryRunCoordinator {
  let currentRun: ApiRestartRecoveryRun | null = null

  const begin = () => {
    currentRun?.controller.abort()
    const run = { token: Symbol('api-restart-recovery'), controller: new AbortController() }
    currentRun = run
    return run
  }

  const isCurrent = (run: ApiRestartRecoveryRun) =>
    currentRun?.token === run.token && !run.controller.signal.aborted

  const cancel = (run: ApiRestartRecoveryRun) => {
    run.controller.abort()
    if (currentRun?.token === run.token) currentRun = null
  }

  const finish = (run: ApiRestartRecoveryRun) => {
    if (currentRun?.token === run.token) currentRun = null
  }

  return { begin, cancel, finish, isCurrent }
}

export const apiRestartRecoveryRuns = createApiRestartRecoveryRunCoordinator()

export async function orchestrateApiRestartRecovery({
  baselineInstanceId,
  initialOutageObserved = false,
  probe,
  refreshActiveData,
  signal,
  intervalMs = 750,
  maxAttempts = 60,
  delay = abortableDelay,
}: ApiRestartRecoveryOptions): Promise<ApiRestartRecoveryOutcome> {
  const baseline = normalizedInstanceId(baselineInstanceId)
  let outageObserved = initialOutageObserved

  if (signal.aborted) return { status: 'cancelled', outageObserved }
  if (maxAttempts < 1) return { status: 'timeout', outageObserved }

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    if (signal.aborted) return { status: 'cancelled', outageObserved }

    let health: ApiHealthSnapshot | null = null
    try {
      health = await probe(signal)
    } catch {
      if (signal.aborted) return { status: 'cancelled', outageObserved }
      outageObserved = true
    }

    if (signal.aborted) return { status: 'cancelled', outageObserved }

    if (health?.status === 'ok') {
      const current = getApiInstanceId(health)
      const changedInstance = Boolean(baseline && current && current !== baseline)
      const legacyOutageRecovery = outageObserved && (!baseline || !current)

      if (changedInstance || legacyOutageRecovery) {
        await refreshActiveData()
        if (signal.aborted) return { status: 'cancelled', outageObserved }
        return { status: 'recovered', outageObserved }
      }
    } else if (health) {
      outageObserved = true
    }

    if (attempt < maxAttempts && intervalMs > 0) {
      await delay(intervalMs, signal)
      if (signal.aborted) return { status: 'cancelled', outageObserved }
    }
  }

  return { status: 'timeout', outageObserved }
}
