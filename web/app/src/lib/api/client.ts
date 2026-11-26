import { camelizeKeys, decamelizeKeys } from 'humps';

import { useAuthStore } from '@/stores/authStore';
import {
  normaliseRoute,
  shouldSampleApiSuccess,
  trackError,
  trackPerformance,
} from '@/lib/analytics';
import { API_BASE_URL } from './base';

export { API_BASE_URL } from './base';

/**
 * Header name the backend reads to resolve the active tenant.
 *
 * The backend cross-checks this header against the authenticated JWT's
 * ``tenant_id`` claim and rejects mismatches with a 403, so injecting it on
 * every call gives the frontend two benefits:
 *   1. Tenant resolution works even on bare ``localhost`` (no subdomain).
 *   2. If someone tampers with the session or the cookie domain bleeds, the
 *      403 surfaces immediately and we drop the session.
 */
const TENANT_HEADER = 'X-Tenant-ID';

/** Substring the backend returns in the 403 ``detail`` for a tenant mismatch. */
const TENANT_MISMATCH_DETAIL = 'does not belong to this tenant';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function shouldInjectTenantHeader(path: string, headers: Headers): boolean {
  if (headers.has(TENANT_HEADER)) {
    return false;
  }
  // Auth endpoints resolve tenant from the host subdomain because the user
  // is either not yet logged in (login) or the session is being torn down
  // (logout). Sending an inconsistent header here would block valid flows.
  return !path.startsWith('/auth/');
}

function forceLogoutAndRedirect(): void {
  if (typeof window === 'undefined') {
    useAuthStore.getState().logout();
    return;
  }
  const alreadyOnLogin = window.location.pathname === '/login';
  useAuthStore.getState().logout();
  if (!alreadyOnLogin) {
    window.location.href = '/login';
  }
}

function reportApiFailure(
  method: string,
  path: string,
  startedAt: number,
  errorType: 'network' | 'http_error',
  httpStatus?: number,
): void {
  if (!useAuthStore.getState().isAuthenticated) return;
  trackPerformance('api_request', Date.now() - startedAt, {
    method,
    path,
    outcome: errorType,
    http_status: httpStatus ?? null,
  });
  trackError('api_request_failed', {
    method,
    path,
    error_type: errorType,
    http_status: httpStatus ?? null,
  });
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const startedAt = Date.now();
  const normalisedPath = normaliseRoute(path);
  const method = options.method ?? 'GET';
  const sampleSuccess = shouldSampleApiSuccess();
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  if (shouldInjectTenantHeader(path, headers)) {
    const tenantId = useAuthStore.getState().user?.tenantId;
    if (tenantId) {
      headers.set(TENANT_HEADER, tenantId);
    }
  }

  let body: BodyInit | null | undefined = options.body;
  if (
    body &&
    typeof body === 'object' &&
    !(body instanceof FormData) &&
    !(body instanceof URLSearchParams) &&
    !(body instanceof Blob) &&
    !(body instanceof ArrayBuffer) &&
    typeof (body as ReadableStream).getReader !== 'function'
  ) {
    body = JSON.stringify(decamelizeKeys(body as unknown as Record<string, unknown>));
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
      body,
      credentials: 'include',
    });
  } catch (error) {
    reportApiFailure(method, normalisedPath, startedAt, 'network');
    throw error;
  }

  if (response.status === 401) {
    const isAuthEndpoint = path.startsWith('/auth/');
    const alreadyOnLogin = typeof window !== 'undefined' && window.location.pathname === '/login';
    if (!isAuthEndpoint && !alreadyOnLogin) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }
    reportApiFailure(method, normalisedPath, startedAt, 'http_error', response.status);
    throw new ApiError('Unauthorized', 401);
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: response.statusText }));
    const message = errorBody.detail || errorBody.message || response.statusText;
    // A 403 whose detail says "does not belong to this tenant" means the
    // session and the requested tenant are out of sync. There is no valid
    // recovery path inside the app shell: re-authenticate on the right
    // tenant subdomain.
    if (
      response.status === 403 &&
      typeof message === 'string' &&
      message.toLowerCase().includes(TENANT_MISMATCH_DETAIL)
    ) {
      forceLogoutAndRedirect();
    }
    reportApiFailure(method, normalisedPath, startedAt, 'http_error', response.status);
    throw new ApiError(message, response.status);
  }

  if (sampleSuccess && useAuthStore.getState().isAuthenticated) {
    trackPerformance('api_request', Date.now() - startedAt, {
      method,
      path: normalisedPath,
      outcome: 'success',
      http_status: response.status,
      sampled: true,
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const data = await response.json();
  return camelizeKeys(data) as T;
}

export const api = {
  get: <T>(path: string, options?: RequestInit) => apiRequest<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestInit) =>
    apiRequest<T>(path, { ...options, method: 'POST', body: body as BodyInit }),
  patch: <T>(path: string, body?: unknown, options?: RequestInit) =>
    apiRequest<T>(path, { ...options, method: 'PATCH', body: body as BodyInit }),
  put: <T>(path: string, body?: unknown, options?: RequestInit) =>
    apiRequest<T>(path, { ...options, method: 'PUT', body: body as BodyInit }),
  delete: <T>(path: string, options?: RequestInit) =>
    apiRequest<T>(path, { ...options, method: 'DELETE' }),
};
