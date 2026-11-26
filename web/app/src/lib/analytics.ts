import { API_BASE_URL } from './api/base';
import { useAuthStore } from '@/stores/authStore';

export type AnalyticsCategory = 'screen_view' | 'action' | 'error' | 'performance' | 'session';
export type AnalyticsValue = string | number | boolean | null;
export type AnalyticsProperties = Record<string, AnalyticsValue>;

type AnalyticsEvent = {
  category: AnalyticsCategory;
  name: string;
  occurred_at: string;
  session_id: string;
  properties: AnalyticsProperties;
};

const FLUSH_INTERVAL_MS = 15_000;
const BATCH_SIZE = 20;
const MAX_QUEUE_SIZE = 100;
const API_SUCCESS_SAMPLE_RATE = 0.1;
let sessionId = createId();
let queue: AnalyticsEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let flushInFlight = false;

function createId(): string {
  return globalThis.crypto?.randomUUID?.() ??
    'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
      const random = Math.floor(Math.random() * 16);
      return (character === 'x' ? random : (random & 0x3) | 0x8).toString(16);
    });
}

export function normaliseRoute(path: string): string {
  const cleanPath = path.split('?')[0].split('#')[0] || '/';
  return cleanPath
    .split('/')
    .map((segment) => {
      if (/^\d+$/.test(segment)) return ':id';
      if (/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(segment)) {
        return ':id';
      }
      return /^[A-Za-z0-9_-]{16,}$/.test(segment) ? ':id' : segment;
    })
    .join('/')
    .slice(0, 200);
}

function screenName(route: string): string {
  const name = route
    .replace(/[^A-Za-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase();
  return (name || 'root').slice(0, 80);
}

function scheduleFlush(): void {
  if (flushTimer || flushInFlight || queue.length === 0) return;
  flushTimer = setTimeout(() => {
    flushTimer = null;
    void flushAnalytics();
  }, FLUSH_INTERVAL_MS);
}

function sanitiseProperties(properties: AnalyticsProperties): AnalyticsProperties {
  return Object.fromEntries(
    Object.entries(properties).map(([key, value]) => [
      key,
      ['path', 'previous_route', 'route'].includes(key) && typeof value === 'string'
        ? normaliseRoute(value)
        : value,
    ]),
  );
}

export function captureAnalytics(
  category: AnalyticsCategory,
  name: string,
  properties: AnalyticsProperties = {},
): void {
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
  });
  if (queue.length > MAX_QUEUE_SIZE) queue = queue.slice(-MAX_QUEUE_SIZE);
  if (queue.length >= BATCH_SIZE) {
    void flushAnalytics();
  } else {
    scheduleFlush();
  }
}

export async function flushAnalytics(): Promise<void> {
  if (flushInFlight || queue.length === 0) return;
  const tenantId = useAuthStore.getState().user?.tenantId;
  if (!tenantId) return;

  flushInFlight = true;
  const batch = queue.splice(0, BATCH_SIZE);
  try {
    const response = await fetch(`${API_BASE_URL}/analytics/events`, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Tenant-ID': tenantId,
      },
      body: JSON.stringify({ events: batch }),
      credentials: 'include',
      keepalive: true,
    });
    if (!response.ok && response.status >= 500) {
      queue = [...batch, ...queue].slice(-MAX_QUEUE_SIZE);
    }
  } catch {
    queue = [...batch, ...queue].slice(-MAX_QUEUE_SIZE);
  } finally {
    flushInFlight = false;
    if (queue.length > 0) scheduleFlush();
  }
}

export function resetAnalyticsSession(): void {
  queue = [];
  sessionId = createId();
  captureAnalytics('session', 'session_started', { source: 'auth_change' });
}

export function trackScreen(route: string, previousRoute?: string): void {
  const normalised = normaliseRoute(route);
  captureAnalytics('screen_view', screenName(normalised), {
    route: normalised,
    previous_route: previousRoute ? normaliseRoute(previousRoute) : null,
  });
}

export function trackAction(name: string, properties: AnalyticsProperties = {}): void {
  captureAnalytics('action', name, properties);
}

export function trackError(name: string, properties: AnalyticsProperties = {}): void {
  captureAnalytics('error', name, properties);
}

export function trackPerformance(
  name: string,
  durationMs: number,
  properties: AnalyticsProperties = {},
): void {
  captureAnalytics('performance', name, {
    ...properties,
    duration_ms: Math.round(durationMs * 100) / 100,
  });
}

export function shouldSampleApiSuccess(): boolean {
  return Math.random() < API_SUCCESS_SAMPLE_RATE;
}

export function startBrowserAnalytics(): () => void {
  const onError = (event: ErrorEvent) => {
    trackError('unhandled_browser_error', {
      error_type: event.error instanceof Error ? event.error.name : 'unknown_error',
      route: normaliseRoute(window.location.pathname),
    });
    void flushAnalytics();
  };
  const onRejection = (event: PromiseRejectionEvent) => {
    trackError('unhandled_promise_rejection', {
      error_type: event.reason instanceof Error ? event.reason.name : 'unknown_error',
      route: normaliseRoute(window.location.pathname),
    });
  };
  const onPageHide = () => void flushAnalytics();
  const reportPageLoad = () => {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
    if (navigation) {
      trackPerformance('page_load', navigation.duration, {
        route: normaliseRoute(window.location.pathname),
        interactive_ms: navigation.domContentLoadedEventEnd,
        load_kind: navigation.type,
      });
    }
  };

  window.addEventListener('error', onError);
  window.addEventListener('unhandledrejection', onRejection);
  window.addEventListener('pagehide', onPageHide);
  if (document.readyState === 'complete') {
    reportPageLoad();
  } else {
    window.addEventListener('load', reportPageLoad, { once: true });
  }

  return () => {
    window.removeEventListener('error', onError);
    window.removeEventListener('unhandledrejection', onRejection);
    window.removeEventListener('pagehide', onPageHide);
    window.removeEventListener('load', reportPageLoad);
    void flushAnalytics();
  };
}
