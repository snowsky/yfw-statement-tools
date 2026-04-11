/**
 * Base API request helper for statement-tools.
 *
 * In plugin/sidecar mode: paths are relative to /api/v1 — nginx proxies them to
 * the backend. Authorization header is forwarded from localStorage token set by
 * the main YFW app.
 *
 * In standalone mode: same relative paths work via the dev proxy or nginx.
 * API key auth uses the X-API-Key header if a token is stored.
 */

import { getVisitorId, getPublicTenantId } from '@/lib/visitor'

const BASE = '/api/v1'

export async function apiRequest<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = localStorage.getItem('token')
  const apiKey = localStorage.getItem('statement_tools_api_key')

  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  } else if (apiKey) {
    headers['X-API-Key'] = apiKey
  } else {
    // ── Public Visitor Headers ──────────────────────────────────────────
    const visitorId = getVisitorId()
    const tenantId = getPublicTenantId()
    if (visitorId) headers['X-Public-Visitor-Id'] = visitorId
    if (tenantId) headers['X-Public-Tenant-Id'] = tenantId
    headers['X-Public-Plugin-Id'] = 'statement-tools'
  }

  // Don't set Content-Type for FormData — browser sets it with boundary
  const isFormData = init.body instanceof FormData
  if (!isFormData) {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
  })

  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText)
    let detail = text
    try {
      detail = JSON.parse(text)?.detail ?? text
    } catch {
      // use raw text
    }
    throw new Error(detail || `HTTP ${response.status}`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

/**
 * Like apiRequest but returns the raw Response Blob (for file downloads).
 * Throws on non-2xx responses with the same error format as apiRequest.
 */
export async function apiBlobRequest(path: string, init: RequestInit = {}): Promise<Blob> {
  const token = localStorage.getItem('token')
  const apiKey = localStorage.getItem('statement_tools_api_key')

  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  } else if (apiKey) {
    headers['X-API-Key'] = apiKey
  }

  const response = await fetch(`${BASE}${path}`, { ...init, headers })

  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText)
    let detail = text
    try {
      detail = JSON.parse(text)?.detail ?? text
    } catch {
      // use raw text
    }
    throw new Error(detail || `HTTP ${response.status}`)
  }

  return response.blob()
}
