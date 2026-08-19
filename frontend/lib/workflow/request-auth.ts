import { getApiAuthHeaders, type ApiAuthHeaders } from '@/lib/api/auth-headers'

export function workflowRequestAuthHeaders(authorization?: string | null): ApiAuthHeaders {
  return getApiAuthHeaders(authorization)
}

export function forwardedRequestAuthHeaders(request: Request): ApiAuthHeaders {
  const authorization = request.headers.get('authorization')
  const fleetToken = request.headers.get('x-api-token')
  const developmentIdentity = request.headers.get('x-opencli-development-identity')
  const csrf = request.headers.get('x-opencli-csrf')
  const cookie = request.headers.get('cookie')
  return {
    ...(authorization ? { Authorization: authorization } : {}),
    ...(fleetToken ? { 'X-API-Token': fleetToken } : {}),
    ...(csrf ? { 'X-OpenCLI-CSRF': csrf } : {}),
    ...(cookie ? { Cookie: cookie } : {}),
    ...(developmentIdentity
      ? { 'X-OpenCLI-Development-Identity': developmentIdentity }
      : {}),
  }
}
