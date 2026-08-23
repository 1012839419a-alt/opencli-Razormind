import { forwardedRequestAuthHeaders } from '@/lib/workflow/request-auth'

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://127.0.0.1:8031'

/** Protect Next-owned mutation routes with the same identity boundary as the API. */
export async function requireAuthenticatedMutation(request: Request): Promise<Response | null> {
  const csrfValid = request.headers.get('x-opencli-csrf') === '1'
  const trustedDevelopmentIdentity =
    process.env.NODE_ENV !== 'production' &&
    request.headers.get('x-opencli-development-identity') === 'local-development'
  if (trustedDevelopmentIdentity) {
    return csrfValid ? null : csrfError()
  }

  let identityResponse: Response
  try {
    identityResponse = await fetch(`${BACKEND_URL}/api/v1/auth/me`, {
      headers: forwardedRequestAuthHeaders(request),
      cache: 'no-store',
    })
  } catch {
    return Response.json(
      { success: false, error: 'AUTH_SERVICE_UNAVAILABLE' },
      { status: 503 },
    )
  }

  if (!identityResponse.ok) {
    return Response.json(
      { success: false, error: 'AUTHENTICATION_REQUIRED' },
      { status: identityResponse.status === 401 ? 401 : 503 },
    )
  }
  if (!csrfValid) return csrfError()
  return null
}

function csrfError(): Response {
  return Response.json(
    { success: false, error: 'CSRF_HEADER_REQUIRED' },
    { status: 403 },
  )
}
