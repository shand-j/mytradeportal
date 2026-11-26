import { resolvePortalSlug } from '../portal/host'
import { API_BASE, getSession } from '../portal/session'

export type AnalyticsCategory = 'screen_view' | 'action' | 'error' | 'performance' | 'session'
export type AnalyticsValue = string | number | boolean | null
export type AnalyticsProperties = Record<string, AnalyticsValue>

type Destination =
  | { type: 'public'; kind: 'quote' | 'invoice'; token: string }
  | { type: 'portal'; slug: string }

type AnalyticsEvent = {
  category: AnalyticsCategory
  name: string
  occurred_at: string
  session_id: string
  properties: AnalyticsProperties
  destination: Destination
}

const FLUSH_INTERVAL_MS = 15_000
const BATCH_SIZE = 20
const MAX_QUEUE_SIZE = 100
const API_SUCCESS_SAMPLE_RATE = 0.1
let sessionId = createId()
let queue: AnalyticsEvent[] = []
let flushTimer: ReturnType<typeof setTimeout> | null = null
let flushInFlight = false

function createId(): string {
  return globalThis.crypto?.randomUUID?.() ??
    'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
      const random = Math.floor(Math.random() * 16)
      return (character === 'x' ? random : (random & 0x3) | 0x8).toString(16)
    })
}

function currentDestination(): Destination | null {
  const match = window.location.pathname.match(/^\/(quote|invoice)\/([^/]+)/)
  if (match) {
    let token = match[2]
    try {
      token = decodeURIComponent(match[2])
    } catch {
      token = match[2]
    }
    return {
      type: 'public',
      kind: match[1] as 'quote' | 'invoice',
      token,
    }
  }
  const slug = resolvePortalSlug()
  return slug && getSession(slug) ? { type: 'portal', slug } : null
}

function destinationKey(destination: Destination): string {
  return destination.type === 'public'
    ? `${destination.type}:${destination.kind}:${destination.token}`
    : `${destination.type}:${destination.slug}`
}

export function normaliseRoute(path: string): string {
  const cleanPath = path.split('?')[0].split('#')[0] || '/'
  return cleanPath
    .split('/')
    .map((segment, index) => {
      if (index === 2 && /^\/(quote|invoice|pay)\//.test(cleanPath)) return ':id'
      if (/^\d+$/.test(segment)) return ':id'
      if (/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(segment)) {
        return ':id'
      }
      return /^[A-Za-z0-9_-]{16,}$/.test(segment) ? ':id' : segment
    })
    .join('/')
    .slice(0, 200)
}

function screenName(route: string): string {
  const name = route
    .replace(/[^A-Za-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase()
  return (name || 'root').slice(0, 80)
}

function scheduleFlush(): void {
  if (flushTimer || flushInFlight || queue.length === 0) return
  flushTimer = setTimeout(() => {
    flushTimer = null
    void flushAnalytics()
  }, FLUSH_INTERVAL_MS)
}

function sanitiseProperties(properties: AnalyticsProperties): AnalyticsProperties {
  return Object.fromEntries(
    Object.entries(properties).map(([key, value]) => [
      key,
      ['path', 'previous_route', 'route'].includes(key) && typeof value === 'string'
        ? normaliseRoute(value)
        : value,
    ]),
  )
}

export function captureAnalytics(
  category: AnalyticsCategory,
  name: string,
  properties: AnalyticsProperties = {},
): void {
  const destination = currentDestination()
  if (!destination) return
  queue.push({
    category,
    name,
    occurred_at: new Date().toISOString(),
    session_id: sessionId,
    properties: {
      platform: 'web',
      app_version: import.meta.env.VITE_APP_VERSION || 'unknown',
      ...sanitiseProperties(properties),
    },
    destination,
  })
  if (queue.length > MAX_QUEUE_SIZE) queue = queue.slice(-MAX_QUEUE_SIZE)
  if (queue.length >= BATCH_SIZE) {
    void flushAnalytics()
  } else {
    scheduleFlush()
  }
}

export async function flushAnalytics(): Promise<void> {
  if (flushInFlight || queue.length === 0) return
  const destination = queue[0].destination
  const key = destinationKey(destination)
  const batch = queue.filter((event) => destinationKey(event.destination) === key).slice(0, BATCH_SIZE)
  const batchIds = new Set(batch)
  const remaining = queue.filter((event) => !batchIds.has(event))
  let url: string
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'Content-Type': 'application/json',
  }

  if (destination.type === 'public') {
    url = `${API_BASE}/public/${destination.kind}/${encodeURIComponent(destination.token)}/analytics`
  } else {
    const session = getSession(destination.slug)
    if (!session) {
      queue = remaining
      if (queue.length > 0) scheduleFlush()
      return
    }
    url = `${API_BASE}/analytics/events`
    headers.Authorization = `Bearer ${session.accessToken}`
  }

  flushInFlight = true
  queue = remaining
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        events: batch.map((event) => ({
          category: event.category,
          name: event.name,
          occurred_at: event.occurred_at,
          session_id: event.session_id,
          properties: event.properties,
        })),
      }),
      keepalive: true,
    })
    if (!response.ok && response.status >= 500) {
      queue = [...batch, ...queue].slice(-MAX_QUEUE_SIZE)
    }
  } catch {
    queue = [...batch, ...queue].slice(-MAX_QUEUE_SIZE)
  } finally {
    flushInFlight = false
    if (queue.length > 0) scheduleFlush()
  }
}

export function resetAnalyticsSession(): void {
  queue = []
  sessionId = createId()
  captureAnalytics('session', 'session_started', { source: 'auth_change' })
}

export function trackScreen(route: string, previousRoute?: string): void {
  const normalised = normaliseRoute(route)
  captureAnalytics('screen_view', screenName(normalised), {
    route: normalised,
    previous_route: previousRoute ? normaliseRoute(previousRoute) : null,
  })
}

export function trackAction(name: string, properties: AnalyticsProperties = {}): void {
  captureAnalytics('action', name, properties)
}

export function trackError(name: string, properties: AnalyticsProperties = {}): void {
  captureAnalytics('error', name, properties)
}

export function trackPerformance(
  name: string,
  durationMs: number,
  properties: AnalyticsProperties = {},
): void {
  captureAnalytics('performance', name, {
    ...properties,
    duration_ms: Math.round(durationMs * 100) / 100,
  })
}

export function shouldSampleApiSuccess(): boolean {
  return Math.random() < API_SUCCESS_SAMPLE_RATE
}

export function startBrowserAnalytics(): () => void {
  const onError = (event: ErrorEvent) => {
    trackError('unhandled_browser_error', {
      error_type: event.error instanceof Error ? event.error.name : 'unknown_error',
      route: normaliseRoute(window.location.pathname),
    })
    void flushAnalytics()
  }
  const onRejection = (event: PromiseRejectionEvent) => {
    trackError('unhandled_promise_rejection', {
      error_type: event.reason instanceof Error ? event.reason.name : 'unknown_error',
      route: normaliseRoute(window.location.pathname),
    })
  }
  const onSessionChange = () => resetAnalyticsSession()
  const onPageHide = () => void flushAnalytics()
  const reportPageLoad = () => {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    if (navigation) {
      trackPerformance('page_load', navigation.duration, {
        route: normaliseRoute(window.location.pathname),
        interactive_ms: navigation.domContentLoadedEventEnd,
        load_kind: navigation.type,
      })
    }
  }

  window.addEventListener('error', onError)
  window.addEventListener('unhandledrejection', onRejection)
  window.addEventListener('pagehide', onPageHide)
  window.addEventListener('mtp:portal-session-changed', onSessionChange)
  if (document.readyState === 'complete') {
    reportPageLoad()
  } else {
    window.addEventListener('load', reportPageLoad, { once: true })
  }

  return () => {
    window.removeEventListener('error', onError)
    window.removeEventListener('unhandledrejection', onRejection)
    window.removeEventListener('pagehide', onPageHide)
    window.removeEventListener('mtp:portal-session-changed', onSessionChange)
    window.removeEventListener('load', reportPageLoad)
    void flushAnalytics()
  }
}
