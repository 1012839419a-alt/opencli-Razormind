// Browser-held Fleet credentials were used by the legacy operator login.
// Human sessions now use an HttpOnly cookie, so this module exists only to
// remove the old value for users upgrading in place. Machine-side Fleet
// authentication is forwarded by server routes and never sourced here.

export const API_AUTH_TOKEN_KEY = 'apiAuthToken'

let legacyTokenCleared = false

export function clearLegacyApiAuthToken(): void {
  if (legacyTokenCleared) return
  try {
    if (typeof localStorage !== 'undefined') localStorage.removeItem(API_AUTH_TOKEN_KEY)
    if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem(API_AUTH_TOKEN_KEY)
    legacyTokenCleared = true
  } catch {
    // Storage can be unavailable in private browsing or hardened browsers.
  }
}

/** Browser API calls authenticate with OIDC or the HttpOnly local cookie. */
export function getApiAuthToken(): string {
  clearLegacyApiAuthToken()
  return ''
}

/** @deprecated Runtime Fleet credentials are no longer accepted in browsers. */
export function setApiAuthToken(_token: string): void {
  clearLegacyApiAuthToken()
}
