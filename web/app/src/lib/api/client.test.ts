import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { apiRequest, api, ApiError } from './client';
import { useAuthStore } from '@/stores/authStore';
import type { User } from '@/types';

const mockFetch = vi.fn();

const TEST_USER: User = {
  id: 'user-1',
  tenantId: 'tenant-aaa',
  fullName: 'Ada Lovelace',
  email: 'ada@example.com',
  phone: null,
  role: 'admin',
  avatarUrl: null,
  isActive: true,
};

describe('ApiError', () => {
  it('sets name, message and status', () => {
    const error = new ApiError('Bad request', 400);
    expect(error.name).toBe('ApiError');
    expect(error.message).toBe('Bad request');
    expect(error.status).toBe(400);
  });
});

describe('apiRequest', () => {
  let originalLogout: () => void;

  beforeEach(() => {
    originalLogout = useAuthStore.getState().logout;
    globalThis.fetch = mockFetch as unknown as typeof fetch;
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
    vi.stubEnv('VITE_API_BASE_URL', 'http://demo.localhost:8000');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    mockFetch.mockRestore();
    vi.restoreAllMocks();
    useAuthStore.setState({ logout: originalLogout });
  });

  it('decamelizes request body and camelizes response data', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ full_name: 'Ada Lovelace', tenant_id: 't1' }),
    });

    const result = await apiRequest<{ fullName: string; tenantId: string }>('/users', {
      method: 'POST',
      body: { fullName: 'Ada Lovelace', tenantId: 't1' } as unknown as BodyInit,
    });

    expect(mockFetch).toHaveBeenCalledWith(
      'http://demo.localhost:8000/users',
      expect.objectContaining({
        method: 'POST',
        headers: expect.any(Headers),
        body: JSON.stringify({ full_name: 'Ada Lovelace', tenant_id: 't1' }),
        credentials: 'include',
      }),
    );

    const requestHeaders = mockFetch.mock.calls[0][1].headers as Headers;
    expect(requestHeaders.get('Content-Type')).toBe('application/json');
    expect(result).toEqual({ fullName: 'Ada Lovelace', tenantId: 't1' });
  });

  it('throws ApiError with server message on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      json: async () => ({ detail: 'Invalid email' }),
    });

    await expect(api.get('/me')).rejects.toSatisfy((err: unknown) => {
      return err instanceof ApiError && err.message === 'Invalid email' && err.status === 422;
    });
  });

  it('logs out and redirects on 401', async () => {
    const logout = vi.fn();
    useAuthStore.setState({ logout: logout as unknown as () => void });
    const originalHref = window.location.href;
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { href: originalHref },
    });

    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Unauthorized' }),
    });

    await expect(api.get('/me')).rejects.toBeInstanceOf(ApiError);
    expect(logout).toHaveBeenCalled();
    expect(window.location.href).toBe('/login');
  });

  it('does not redirect on 401 for auth endpoints', async () => {
    const logout = vi.fn();
    useAuthStore.setState({ logout: logout as unknown as () => void });
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { href: 'http://demo.localhost:3000/login', pathname: '/login' },
    });

    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Unauthorized' }),
    });

    await expect(api.get('/auth/me')).rejects.toBeInstanceOf(ApiError);
    expect(logout).not.toHaveBeenCalled();
    expect(window.location.href).not.toBe('/login');
  });

  it('does not redirect on 401 when already on the login page', async () => {
    const logout = vi.fn();
    useAuthStore.setState({ logout: logout as unknown as () => void });
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { href: 'http://demo.localhost:3000/login', pathname: '/login' },
    });

    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Unauthorized' }),
    });

    await expect(api.get('/tenants/me')).rejects.toBeInstanceOf(ApiError);
    expect(logout).not.toHaveBeenCalled();
    expect(window.location.href).not.toBe('/login');
  });

  it('returns undefined for 204 No Content', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => ({}),
    });

    const result = await api.post<void>('/logout');
    expect(result).toBeUndefined();
  });

  it('falls back to statusText when the error body is not JSON', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
      json: async () => {
        throw new Error('Invalid JSON');
      },
    });

    await expect(api.get('/me')).rejects.toSatisfy((err: unknown) => {
      return err instanceof ApiError && err.message === 'Service Unavailable' && err.status === 503;
    });
  });

  it('does not decamelize FormData bodies', async () => {
    const formData = new FormData();
    formData.append('fullName', 'Ada Lovelace');

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ id: '1' }),
    });

    await apiRequest('/upload', { method: 'POST', body: formData as unknown as BodyInit });

    const sentBody = (mockFetch.mock.calls[0][1] as RequestInit).body;
    expect(sentBody).toBe(formData);
  });

  describe('tenant header injection', () => {
    it('injects X-Tenant-ID from the auth store on data requests', async () => {
      useAuthStore.setState({ user: TEST_USER, isAuthenticated: true, isLoading: false });
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

      await api.get('/contacts');

      const headers = mockFetch.mock.calls[0][1].headers as Headers;
      expect(headers.get('X-Tenant-ID')).toBe('tenant-aaa');
    });

    it('does not inject the tenant header on /auth/* endpoints', async () => {
      useAuthStore.setState({ user: TEST_USER, isAuthenticated: true, isLoading: false });
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      });

      await api.get('/auth/me');

      const headers = mockFetch.mock.calls[0][1].headers as Headers;
      expect(headers.has('X-Tenant-ID')).toBe(false);
    });

    it('omits the tenant header when no user is in the store', async () => {
      // Anonymous request — backend falls back to subdomain resolution.
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      });

      await api.get('/contacts');

      const headers = mockFetch.mock.calls[0][1].headers as Headers;
      expect(headers.has('X-Tenant-ID')).toBe(false);
    });

    it('respects a caller-supplied X-Tenant-ID and does not overwrite it', async () => {
      useAuthStore.setState({ user: TEST_USER, isAuthenticated: true, isLoading: false });
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      });

      await api.get('/contacts', { headers: { 'X-Tenant-ID': 'override-tenant' } });

      const headers = mockFetch.mock.calls[0][1].headers as Headers;
      expect(headers.get('X-Tenant-ID')).toBe('override-tenant');
    });
  });

  describe('tenant mismatch handling', () => {
    it('forces logout and redirects when the backend returns 403 with the tenant-mismatch detail', async () => {
      const logout = vi.fn();
      useAuthStore.setState({
        user: TEST_USER,
        isAuthenticated: true,
        isLoading: false,
        logout: logout as unknown as () => void,
      });
      Object.defineProperty(window, 'location', {
        writable: true,
        value: { href: 'http://demo.localhost:3000/quotes', pathname: '/quotes' },
      });

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
        json: async () => ({ detail: 'Authenticated user does not belong to this tenant' }),
      });

      await expect(api.get('/contacts')).rejects.toBeInstanceOf(ApiError);
      expect(logout).toHaveBeenCalled();
      expect(window.location.href).toBe('/login');
    });

    it('does NOT force logout on unrelated 403 (legitimate permission denied)', async () => {
      const logout = vi.fn();
      useAuthStore.setState({
        user: TEST_USER,
        isAuthenticated: true,
        isLoading: false,
        logout: logout as unknown as () => void,
      });
      Object.defineProperty(window, 'location', {
        writable: true,
        value: { href: 'http://demo.localhost:3000/settings', pathname: '/settings' },
      });

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
        json: async () => ({ detail: 'Insufficient permissions' }),
      });

      await expect(api.get('/users')).rejects.toBeInstanceOf(ApiError);
      expect(logout).not.toHaveBeenCalled();
      expect(window.location.href).not.toBe('/login');
    });

    it('does not double-redirect when the user is already on /login', async () => {
      const logout = vi.fn();
      useAuthStore.setState({
        user: TEST_USER,
        isAuthenticated: true,
        isLoading: false,
        logout: logout as unknown as () => void,
      });
      Object.defineProperty(window, 'location', {
        writable: true,
        value: { href: 'http://demo.localhost:3000/login', pathname: '/login' },
      });

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
        json: async () => ({ detail: 'Authenticated user does not belong to this tenant' }),
      });

      await expect(api.get('/contacts')).rejects.toBeInstanceOf(ApiError);
      expect(logout).toHaveBeenCalled();
      // href must NOT be reassigned, otherwise we get a redirect loop.
      expect(window.location.href).toBe('http://demo.localhost:3000/login');
    });
  });
});
