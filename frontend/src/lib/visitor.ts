const VISITOR_ID_KEY = 'yfw_public_visitor_id'

/**
 * Get or generate a persistent visitor ID for anonymous usage tracking.
 */
export function getVisitorId(): string {
  let id = localStorage.getItem(VISITOR_ID_KEY)
  if (!id) {
    // Use native crypto.randomUUID if available, else fallback to a simple random string
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      id = crypto.randomUUID()
    } else {
      id = Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15)
    }
    localStorage.setItem(VISITOR_ID_KEY, id)
  }
  return id || ''
}

/**
 * Extract tenant ID from URL query parameters.
 */
export function getPublicTenantId(): string | null {
  const params = new URLSearchParams(window.location.search)
  return params.get('t') || params.get('tenantId')
}
