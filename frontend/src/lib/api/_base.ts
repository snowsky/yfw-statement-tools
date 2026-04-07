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
