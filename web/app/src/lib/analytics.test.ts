import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  captureAnalytics,
  flushAnalytics,
  normaliseRoute,
  resetAnalyticsSession,
  trackAction,
} from './analytics';
import { useAuthStore } from '@/stores/authStore';
import type { User } from '@/types';

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

describe('browser analytics', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useAuthStore.setState({ user: TEST_USER, isAuthenticated: true, isLoading: false });
    resetAnalyticsSession();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
  });

  it('normalises ids and removes query strings from routes', () => {
    const id = '123e4567-e89b-42d3-a456-426614174000';
    expect(normaliseRoute(`/quotes/${id}?token=secret`)).toBe('/quotes/:id');
    expect(normaliseRoute('/quote/a-very-long-secret-token')).toBe('/quote/:id');
  });

  it('batches sanitised events with cookie auth and tenant context', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 202 });
    vi.stubGlobal('fetch', fetchMock);
    const id = '123e4567-e89b-42d3-a456-426614174000';

    trackAction('quote_send_submit', {
      entity_type: 'quote',
      entity_id: id,
      route: `/quotes/${id}?token=secret`,
    });
    await flushAnalytics();

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain('/analytics/events');
    expect(options.credentials).toBe('include');
    expect(options.headers['X-Tenant-ID']).toBe('tenant-aaa');
    const body = JSON.parse(options.body as string);
    const action = body.events.find((event: { category: string }) => event.category === 'action');
    expect(action.name).toBe('quote_send_submit');
    expect(action.properties.route).toBe('/quotes/:id');
    expect(options.body).not.toContain('secret');
  });

  it('does not send queued events without an authenticated tenant', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
    captureAnalytics('action', 'dashboard_retry');

    await flushAnalytics();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
