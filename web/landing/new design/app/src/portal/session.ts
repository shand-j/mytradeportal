/**
 * Portal session — the customer JWT minted by the magic-link flow.
 *
 * The token is kept in memory and mirrored to localStorage under a per-slug
 * key (`mtp_portal_{slug}`) so portal sessions on different tenant
 * subdomains never clobber each other. `apiFetch` attaches the bearer token
 * and maps any 401 to a cleared session + a global session-expired event
 * (PortalProvider surfaces the "email me a new link" banner).
 */

export interface StoredSession {
  accessToken: string
  expiresAt: string
  customer: { id: string; full_name: string; email: string }
}

export class SessionExpiredError extends Error {
  constructor() {
    super('Your session has expired')
    this.name = 'SessionExpiredError'
  }
}

export const API_BASE: string = import.meta.env.VITE_API_URL ?? ''

const storageKey = (slug: string) => `mtp_portal_${slug}`

let memorySession: StoredSession | null = null

function emitSessionChanged(): void {
  queueMicrotask(() => window.dispatchEvent(new Event('mtp:portal-session-changed')))
}

function isExpired(session: StoredSession): boolean {
  const expiry = Date.parse(session.expiresAt)
  return Number.isNaN(expiry) || expiry <= Date.now()
}

export function saveSession(slug: string, session: StoredSession): void {
  memorySession = session
  try {
    window.localStorage.setItem(storageKey(slug), JSON.stringify(session))
  } catch {
    // Private browsing / storage disabled — the in-memory copy still works.
  }
  emitSessionChanged()
}

export function getSession(slug: string): StoredSession | null {
  if (memorySession) {
    if (isExpired(memorySession)) {
      clearSession(slug)
      return null
    }
    return memorySession
  }
  try {
    const raw = window.localStorage.getItem(storageKey(slug))
    if (!raw) return null
    const session = JSON.parse(raw) as StoredSession
    if (!session.accessToken || isExpired(session)) {
      clearSession(slug)
      return null
    }
    memorySession = session
    return session
  } catch {
    return null
  }
}

export function clearSession(slug: string): void {
  memorySession = null
  try {
    window.localStorage.removeItem(storageKey(slug))
  } catch {
    // ignore
  }
  emitSessionChanged()
}

/* Global session-expired signal — one subscriber (PortalProvider) in
   practice, but kept as a set so pages could listen too. */
const listeners = new Set<() => void>()

export function onSessionExpired(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function emitSessionExpired(): void {
  listeners.forEach((listener) => listener())
}

/**
 * fetch() wrapper for the authenticated customer API. Attaches the portal
 * bearer token, sets JSON content type for string bodies, and on 401 clears
 * the stored session, notifies subscribers and throws SessionExpiredError.
 */
function reportApiCall(
  path: string,
  method: string,
  startedAt: number,
  outcome: 'success' | 'network' | 'http_error',
  httpStatus?: number,
): void {
  void import('../lib/analytics')
    .then(({ normaliseRoute, shouldSampleApiSuccess, trackError, trackPerformance }) => {
      if (outcome === 'success' && !shouldSampleApiSuccess()) return
      trackPerformance('api_request', Date.now() - startedAt, {
        method,
        path: normaliseRoute(path),
        outcome,
        http_status: httpStatus ?? null,
        sampled: outcome === 'success' || null,
      })
      if (outcome !== 'success') {
        trackError('api_request_failed', {
          method,
          path: normaliseRoute(path),
          error_type: outcome,
          http_status: httpStatus ?? null,
        })
      }
    })
    .catch(() => undefined)
}

export async function apiFetch(
  slug: string,
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const startedAt = Date.now()
  const method = init.method ?? 'GET'
  const session = getSession(slug)
  const headers = new Headers(init.headers)
  if (session) headers.set('Authorization', `Bearer ${session.accessToken}`)
  if (typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch (error) {
    reportApiCall(path, method, startedAt, 'network')
    throw error
  }
  if (!res.ok) reportApiCall(path, method, startedAt, 'http_error', res.status)
  if (res.status === 401 && session) {
    clearSession(slug)
    emitSessionExpired()
    throw new SessionExpiredError()
  }
  if (res.ok) reportApiCall(path, method, startedAt, 'success', res.status)
  return res
}
