import type { SavedJob } from '@/types'
import { getVisitorId } from '@/lib/visitor'

const MAX_JOBS = 50

/**
 * Derive a storage scope so job history is isolated per user identity.
 *
 * Priority:
 *  1. Authenticated sidecar: decode the JWT's user_id / sub claim.
 *  2. Standalone API key: first 8 chars of the key (not a secret, just a discriminator).
 *  3. Public visitor: visitor UUID (already per-browser) + tenant ID from the URL.
 *
 * Two different logged-in users on the same browser will never share history.
 * Two public visitors on different browsers will never share history.
 */
function getScope(): string {
  // 1. Sidecar JWT
  const token = localStorage.getItem('token')
  if (token) {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      const id = payload.user_id ?? payload.sub ?? 'auth'
      return `user_${id}`
    } catch {
      return 'auth_unknown'
    }
  }

  // 2. Standalone API key
  const apiKey = localStorage.getItem('statement_tools_api_key')
  if (apiKey) {
    return `api_${apiKey.slice(0, 8)}`
  }

  // 3. Public visitor — combine visitor UUID with tenant so that the same
  //    browser visiting two different tenants also gets separate histories.
  // Call getVisitorId() (not a raw localStorage read) so the UUID is created
  // on first access; otherwise early calls before any API request would all
  // share the fallback 'anon' key.
  const visitorId = getVisitorId() || 'anon'
  const params = new URLSearchParams(window.location.search)
  const tenantId = params.get('t') ?? params.get('tenantId') ?? 'default'
  return `public_${tenantId}_${visitorId}`
}

function storageKey(): string {
  return `statement_tools_job_history_${getScope()}`
}

export function loadJobs(): SavedJob[] {
  try {
    return JSON.parse(localStorage.getItem(storageKey()) || '[]')
  } catch {
    return []
  }
}

export function saveJob(job: SavedJob): void {
  const key = storageKey()
  const existing = loadJobs()
  const deduped = [job, ...existing.filter(j => j.job_id !== job.job_id)]
  localStorage.setItem(key, JSON.stringify(deduped.slice(0, MAX_JOBS)))
}

export function updateJobStatus(job_id: string, status: string): void {
  const key = storageKey()
  const jobs = loadJobs()
  const updated = jobs.map(j => j.job_id === job_id ? { ...j, status } : j)
  localStorage.setItem(key, JSON.stringify(updated))
}

export function removeJob(job_id: string): void {
  const key = storageKey()
  const jobs = loadJobs().filter(j => j.job_id !== job_id)
  localStorage.setItem(key, JSON.stringify(jobs))
}
