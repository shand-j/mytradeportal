import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { authService } from './auth';
import type { User } from '@/types';

const mockFetch = vi.fn();

describe('authService', () => {
  beforeEach(() => {
    globalThis.fetch = mockFetch as unknown as typeof fetch;
    vi.stubEnv('VITE_API_BASE_URL', 'http://demo.localhost:8000');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    mockFetch.mockRestore();
  });

  it('login sends credentials and returns the user', async () => {
    const user: User = {
      id: 'u1',
      tenantId: 't1',
      fullName: 'Admin User',
      email: 'admin@demo.local',
      phone: null,
      role: 'admin',
      avatarUrl: null,
      isActive: true,
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        id: 'u1',
        tenant_id: 't1',
        full_name: 'Admin User',
        email: 'admin@demo.local',
        phone: null,
        role: 'admin',
        avatar_url: null,
        is_active: true,
      }),
    });

    const result = await authService.login({ email: 'admin@demo.local', password: 'password123' });

    expect(mockFetch).toHaveBeenCalledWith(
      'http://demo.localhost:8000/auth/login',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'admin@demo.local', password: 'password123' }),
        credentials: 'include',
      }),
    );
    expect(result).toEqual(user);
  });

  it('logout posts to /auth/logout', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => ({}),
    });

    await authService.logout();

    expect(mockFetch).toHaveBeenCalledWith(
      'http://demo.localhost:8000/auth/logout',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    );
  });

  it('me fetches current user', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        id: 'u2',
        tenant_id: 't1',
        full_name: 'Technician User',
        email: 'tech@demo.local',
        phone: null,
        role: 'technician',
        avatar_url: null,
        is_active: true,
      }),
    });

    const result = await authService.me();

    expect(mockFetch).toHaveBeenCalledWith(
      'http://demo.localhost:8000/auth/me',
      expect.objectContaining({ method: 'GET', credentials: 'include' }),
    );
    expect(result).toMatchObject({ fullName: 'Technician User', role: 'technician' });
  });
});
