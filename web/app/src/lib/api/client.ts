import { camelizeKeys, decamelizeKeys } from 'humps';

import { useAuthStore } from '@/stores/authStore';

function resolveApiBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl && envUrl !== '') {
    return envUrl;
  }
  if (typeof window !== 'undefined') {
    // Use the page's hostname so subdomain-based tenant resolution works
    // when the UI is served from demo.localhost:3000.
    return `http://${window.location.hostname}:8000`;
  }
  return 'http://localhost:8000';
}

export const API_BASE_URL = resolveApiBaseUrl();

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

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
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

  const response = await fetch(url, {
    ...options,
    headers,
    body,
    credentials: 'include',
  });

  if (response.status === 401) {
    const isAuthEndpoint = path.startsWith('/auth/');
    const alreadyOnLogin = typeof window !== 'undefined' && window.location.pathname === '/login';
    if (!isAuthEndpoint && !alreadyOnLogin) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }
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
    throw new ApiError(message, response.status);
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
