export const AUTH_REQUIRED_EVENT = 'opencli:auth-required'

export type AuthRequiredEventDetail = Readonly<{
  identityGeneration: number
}>

export function shouldInvalidateIdentityForGeneration(
  requestGeneration: unknown,
  currentGeneration: number,
): boolean {
  return typeof requestGeneration === 'number' && requestGeneration === currentGeneration
}

export function notifyAuthRequired(identityGeneration: number): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(
    new CustomEvent<AuthRequiredEventDetail>(AUTH_REQUIRED_EVENT, {
      detail: { identityGeneration },
    }),
  )
}
