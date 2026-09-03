export const API_HEALTH_REQUEST_TIMEOUT_MS = 2_500

export type ApiRecoveryResult = 'recovered' | 'timeout' | 'cancelled'

export type IdentityValidationRecoveryResult = 'completed' | 'stopped' | 'timeout' | 'cancelled'

export type RecoveryEpoch = number

// A 401 carrying this marker rejects the transport boundary. The client may
// retain identity only when the failed request actually carried a non-empty
// X-API-Token; without that request metadata the bearer itself may be an
// expired local session rejected by FleetAuthMiddleware.
export const FLEET_AUTH_ERROR_CODE = 'fleet_auth_invalid'

export class RecoverySupersededError extends Error {
  constructor() {
    super('Identity recovery was superseded by a newer session change.')
    this.name = 'RecoverySupersededError'
  }
}

export type IdentityRecoveryCoordinator = {
  beginEpoch: () => RecoveryEpoch
  invalidate: () => void
  isCurrent: (epoch: RecoveryEpoch) => boolean
  run: <T>(
    token: string,
    recover: (epoch: RecoveryEpoch) => Promise<T>,
    epoch?: RecoveryEpoch,
  ) => Promise<T>
}

export type ApiLivenessPollOptions = {
  initialDelayMs?: number
  intervalMs?: number
  maxAttempts?: number
  requireUnavailableBeforeRecovery?: boolean
  delay?: (milliseconds: number) => Promise<void>
  isCancelled?: () => boolean
}

const sleep = (milliseconds: number) =>
  new Promise<void>((resolve) => {
    window.setTimeout(resolve, milliseconds)
  })

export function getApiErrorStatus(error: unknown): number | undefined {
  if (!error || typeof error !== 'object' || !('status' in error)) return undefined
  const status = (error as { status?: unknown }).status
  return typeof status === 'number' ? status : undefined
}

export function getApiErrorCode(error: unknown): string | undefined {
  if (!error || typeof error !== 'object' || !('code' in error)) return undefined
  const code = (error as { code?: unknown }).code
  return typeof code === 'string' ? code : undefined
}

export function hasFleetTransportCredential(value: unknown): boolean {
  return typeof value === 'string' && value.trim().length > 0
}

export function isFleetAuthError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  return (
    getApiErrorStatus(error) === 401 &&
    getApiErrorCode(error) === FLEET_AUTH_ERROR_CODE &&
    (error as { fleetTransportCredentialAttached?: unknown })
      .fleetTransportCredentialAttached === true
  )
}

export function isAuthRejection(error: unknown): boolean {
  const status = getApiErrorStatus(error)
  if (isFleetAuthError(error)) return false
  return status === 401 || status === 403
}

export type IdentityRecoveryErrorKind = 'auth-rejection' | 'transient' | 'incompatible'

export function classifyIdentityRecoveryError(error: unknown): IdentityRecoveryErrorKind {
  const status = getApiErrorStatus(error)
  if (isFleetAuthError(error)) return 'incompatible'
  if (status === 401 || status === 403) return 'auth-rejection'
  if (status === undefined || status === 408 || status === 429 || status >= 500) return 'transient'
  return 'incompatible'
}

export function createIdentityRecoveryCoordinator(): IdentityRecoveryCoordinator {
  let currentEpoch = 0
  let operation: {
    token: string
    epoch: RecoveryEpoch
    promise: Promise<unknown>
  } | null = null
  let operationTail: Promise<void> = Promise.resolve()

  const beginEpoch = () => {
    currentEpoch += 1
    return currentEpoch
  }

  const invalidate = () => {
    beginEpoch()
  }

  const isCurrent = (epoch: RecoveryEpoch) => epoch === currentEpoch

  const run: IdentityRecoveryCoordinator['run'] = <T>(
    token: string,
    recover: (epoch: RecoveryEpoch) => Promise<T>,
    requestedEpoch?: RecoveryEpoch,
  ) => {
    if (
      operation &&
      operation.epoch === currentEpoch &&
      operation.token === token &&
      (requestedEpoch === undefined || requestedEpoch === currentEpoch)
    ) {
      return operation.promise as Promise<T>
    }

    const operationEpoch = requestedEpoch ?? beginEpoch()
    if (!isCurrent(operationEpoch) || (operation && operation.epoch === operationEpoch)) {
      return Promise.reject(new RecoverySupersededError())
    }

    const promise = operationTail.then(() => {
      if (!isCurrent(operationEpoch)) throw new RecoverySupersededError()
      return recover(operationEpoch)
    })
    operation = { token, epoch: operationEpoch, promise }
    operationTail = promise.then(
      () => undefined,
      () => undefined,
    )
    return promise
  }

  return { beginEpoch, invalidate, isCurrent, run }
}

export async function retryIdentityValidation(
  validate: () => Promise<void>,
  handleFailure: (error: unknown) => Promise<boolean>,
  waitForLiveness: () => Promise<ApiRecoveryResult>,
  maxAttempts = 3,
): Promise<IdentityValidationRecoveryResult> {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      await validate()
      return 'completed'
    } catch (error) {
      if (!(await handleFailure(error))) return 'stopped'
    }
    if (attempt === maxAttempts - 1) return 'stopped'
    const liveness = await waitForLiveness()
    if (liveness === 'cancelled') return 'cancelled'
    if (liveness === 'timeout') return 'timeout'
  }
  return 'stopped'
}

export async function waitForApiLiveness(
  probe: () => Promise<boolean>,
  {
    initialDelayMs = 1_500,
    intervalMs = 2_500,
    maxAttempts = 8,
    requireUnavailableBeforeRecovery = false,
    delay = sleep,
    isCancelled = () => false,
  }: ApiLivenessPollOptions = {},
): Promise<ApiRecoveryResult> {
  if (isCancelled()) return 'cancelled'
  if (maxAttempts < 1) return 'timeout'
  if (initialDelayMs > 0) {
    if (isCancelled()) return 'cancelled'
    await delay(initialDelayMs)
    if (isCancelled()) return 'cancelled'
  }
  let unavailableObserved = !requireUnavailableBeforeRecovery

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    if (isCancelled()) return 'cancelled'
    let available = false
    try {
      available = await probe()
    } catch {
      // An unavailable API is the expected condition while recovery is active.
    }
    if (isCancelled()) return 'cancelled'
    if (!available) unavailableObserved = true
    if (available && unavailableObserved) return 'recovered'
    if (attempt < maxAttempts && intervalMs > 0) {
      if (isCancelled()) return 'cancelled'
      await delay(intervalMs)
      if (isCancelled()) return 'cancelled'
    }
  }
  return 'timeout'
}
