import {
  getIdentityAccessToken,
  hasDevelopmentSession,
  isDevelopmentLoginAllowed,
} from '@/lib/auth/session'

export type ApiAuthHeaders = {
  Authorization?: string
  'X-API-Token'?: string
  'X-OpenCLI-Development-Identity'?: string
  'X-OpenCLI-CSRF'?: string
  Cookie?: string
}

export function getApiAuthHeaders(authorizationOverride?: string | null): ApiAuthHeaders {
  const identityToken = getIdentityAccessToken()
  const developmentIdentity =
    isDevelopmentLoginAllowed() && hasDevelopmentSession()
      ? { 'X-OpenCLI-Development-Identity': 'local-development' as const }
      : {}

  if (authorizationOverride) {
    return {
      Authorization: authorizationOverride,
      'X-OpenCLI-CSRF': '1',
      ...developmentIdentity,
    }
  }
  if (identityToken) {
    return {
      Authorization: `Bearer ${identityToken}`,
      'X-OpenCLI-CSRF': '1',
      ...developmentIdentity,
    }
  }
  return {
    'X-OpenCLI-CSRF': '1',
    ...developmentIdentity,
  }
}
