import axios, { type InternalAxiosRequestConfig } from 'axios'

import { getApiAuthHeaders } from './auth-headers'
import { notifyAuthRequired } from './auth-events'

export const apiClient = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export const rootClient = axios.create({
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

// Attach OIDC identity centrally. Local human sessions are carried only by
// the browser-managed HttpOnly cookie; browsers never attach Fleet tokens.
const attachAuthHeaders = (config: InternalAxiosRequestConfig) => {
  const headers = getApiAuthHeaders()
  if (headers.Authorization && !config.headers.Authorization) {
    config.headers.Authorization = headers.Authorization
  }
  if (
    headers['X-OpenCLI-Development-Identity'] &&
    !config.headers['X-OpenCLI-Development-Identity']
  ) {
    config.headers['X-OpenCLI-Development-Identity'] =
      headers['X-OpenCLI-Development-Identity']
  }
  const method = config.method?.toUpperCase() ?? 'GET'
  if (!SAFE_METHODS.has(method) && !config.headers['X-OpenCLI-CSRF']) {
    config.headers['X-OpenCLI-CSRF'] = '1'
  }
  return config
}

apiClient.interceptors.request.use(attachAuthHeaders)
rootClient.interceptors.request.use(attachAuthHeaders)

// Plan IR issue 07: a 422 from the Plans API carries a node-anchored error
// LIST in `detail` (backend.plan_ir.validation.PlanValidationError.to_dict()
// shape), not a string. Every other endpoint's `detail` is a string or absent.
// Stringifying `detail` unconditionally (the old behavior) turned that list
// into a useless comma-joined blob for every caller and threw away the
// node_id/edge_id anchors the canvas needs to render errors in place — so
// array details are left OUT of the message and attached raw as `.detail`
// instead, additive to every existing caller that only reads `.message`.
const normalizeApiError = (err: unknown) => {
  if (axios.isAxiosError(err)) {
    const authenticationAttempt =
      err.config?.url === '/auth/login' || err.config?.url === '/auth/setup'
    if (err.response?.status === 401 && !authenticationAttempt) notifyAuthRequired()
    const detail = err.response?.data?.detail
    const detailIsList = Array.isArray(detail)
    const message =
      err.response?.data?.error || (detailIsList ? undefined : detail) || err.message || 'Unknown error'
    const normalized = new Error(message) as Error & { detail?: unknown; status?: number }
    if (detailIsList) normalized.detail = detail
    normalized.status = err.response?.status
    return Promise.reject(normalized)
  }
  return Promise.reject(err)
}

apiClient.interceptors.response.use(
  (res) => res,
  normalizeApiError
)

rootClient.interceptors.response.use(
  (res) => res,
  normalizeApiError
)
