import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { waitFor } from '@testing-library/react';

import { useJobs, useJob, useCreateJob, useUpdateJob, useTransitionJobStatus, useDeleteJob } from './jobs';
import { renderHookWithProviders, createTestQueryClient } from '@/test/test-utils';
import type { Job } from '@/types';

const mockFetch = vi.fn();
const API_BASE_URL = 'http://demo.localhost:8000';

function buildResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 422 ? 'Unprocessable Entity' : 'OK',
    json: async () => body,
  };
}

function lastFetchBody(): Record<string, unknown> {
  const init = (mockFetch.mock.calls.at(-1) as [string, RequestInit])[1];
  return JSON.parse(init.body as string);
}

function mockBackendJob(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    title: `J-${id}`,
    contact_id: 'c1',
    contact: { id: 'c1', name: 'Alice Smith', email: null, phone: '07700 000000', address: null, postcode: null, notes: null, avatar_url: null, created_at: '2025-01-01T00:00:00Z' },
    quote_id: null,
    status: 'scheduled',
    description: 'Rewire',
    scheduled_start: '2025-01-01T09:00:00',
    scheduled_end: '2025-01-01T17:00:00',
    completed_at: null,
    notes: null,
    photos: [],
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    ...overrides,
  };
}

function mockJobResponse(id: string, overrides: Record<string, unknown> = {}) {
  return buildResponse(mockBackendJob(id, overrides));
}

function renderHookNoAuth<TProps, TResult>(hook: (props: TProps) => TResult) {
  return renderHookWithProviders(hook, { withAuth: false });
}

describe('job hooks', () => {
  beforeEach(() => {
    globalThis.fetch = mockFetch as unknown as typeof fetch;
    vi.stubEnv('VITE_API_BASE_URL', API_BASE_URL);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    mockFetch.mockClear();
  });

  it('useJobs fetches the job list', async () => {
    mockFetch.mockResolvedValueOnce(buildResponse([mockBackendJob('j1')]));

    const { result } = renderHookNoAuth(() => useJobs());

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/jobs`,
      expect.objectContaining({ method: 'GET' }),
    );

    const data = result.current.data as Job[];
    expect(data).toHaveLength(1);
    expect(data[0].serviceType).toBe('Rewire');
    expect(data[0].reference).toBe('J-j1');
    expect(data[0].scheduledDate).toBe('2025-01-01');
  });

  it('useJob fetches a single job', async () => {
    mockFetch.mockResolvedValueOnce(mockJobResponse('j1', { status: 'in_progress' }));

    const { result } = renderHookNoAuth(() => useJob('j1'));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/jobs/j1`,
      expect.objectContaining({ method: 'GET' }),
    );
    expect((result.current.data as Job).status).toBe('in_progress');
  });

  it('useJob does not fetch when id is empty', () => {
    renderHookNoAuth(() => useJob(''));
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('useCreateJob posts a decamelized body and invalidates the list key', async () => {
    mockFetch.mockResolvedValueOnce(mockJobResponse('j-new'));

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['jobs'], []);

    const { result } = renderHookWithProviders(() => useCreateJob(), { queryClient, withAuth: false });

    await result.current.mutateAsync({
      customerId: 'c1',
      reference: 'J-NEW',
      serviceType: 'Rewire',
      scheduledDate: '2025-01-01',
      propertyAddress: '1 Road',
      value: 100,
      description: 'Full rewire',
      status: 'scheduled',
      quoteId: null,
      scheduledTimeStart: null,
      scheduledTimeEnd: null,
      technicianId: null,
      technicianName: null,
      completionNotes: null,
      photos: [],
    });

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/jobs`,
      expect.objectContaining({ method: 'POST' }),
    );

    expect(lastFetchBody()).toHaveProperty('contact_id', 'c1');
    expect(lastFetchBody()).toHaveProperty('title', 'J-NEW');
    expect(lastFetchBody()).toHaveProperty('description', 'Rewire\n1 Road\nFull rewire');
    expect(lastFetchBody()).toHaveProperty('scheduled_start', '2025-01-01T09:00');
    expect(lastFetchBody()).toHaveProperty('scheduled_end', '2025-01-01T17:00');
    expect(queryClient.getQueryCache().find({ queryKey: ['jobs'] })?.state.isInvalidated).toBe(true);
  });

  it('useUpdateJob patches a job and invalidates both keys', async () => {
    mockFetch.mockResolvedValueOnce(mockJobResponse('j1', { value: 200 }));

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['jobs'], []);
    queryClient.setQueryData(['job', 'j1'], {});

    const { result } = renderHookWithProviders(() => useUpdateJob(), { queryClient, withAuth: false });

    await result.current.mutateAsync({ id: 'j1', data: { serviceType: 'Upgrade', propertyAddress: '2 Lane', scheduledDate: '2025-02-02' } as Partial<Job> });

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/jobs/j1`,
      expect.objectContaining({ method: 'PATCH' }),
    );

    expect(lastFetchBody()).toHaveProperty('description', 'Upgrade\n2 Lane');
    expect(lastFetchBody()).toHaveProperty('scheduled_start', '2025-02-02T09:00');
    expect(lastFetchBody()).toHaveProperty('scheduled_end', '2025-02-02T17:00');
    expect(queryClient.getQueryCache().find({ queryKey: ['job', 'j1'] })?.state.isInvalidated).toBe(true);
    expect(queryClient.getQueryCache().find({ queryKey: ['jobs'] })?.state.isInvalidated).toBe(true);
  });

  it.each([
    ['start', 'in_progress'],
    ['complete', 'completed'],
    ['cancel', 'cancelled'],
  ] as const)('useTransitionJobStatus(%s) patches /jobs/:id/%s', async (action, expectedStatus) => {
    mockFetch.mockResolvedValue(mockJobResponse('j1', { status: expectedStatus }));

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['jobs'], []);
    queryClient.setQueryData(['job', 'j1'], {});

    const { result } = renderHookWithProviders(() => useTransitionJobStatus(action), { queryClient, withAuth: false });

    await result.current.mutateAsync('j1');

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/jobs/j1/${action}`,
      expect.objectContaining({ method: 'POST' }),
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect((result.current.data as Job).status).toBe(expectedStatus);
    expect(queryClient.getQueryCache().find({ queryKey: ['job', 'j1'] })?.state.isInvalidated).toBe(true);
  });

  it('useDeleteJob deletes a job and invalidates the list key', async () => {
    mockFetch.mockResolvedValueOnce(buildResponse(null, 204));

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['jobs'], []);

    const { result } = renderHookWithProviders(() => useDeleteJob(), { queryClient, withAuth: false });

    await result.current.mutateAsync('j1');

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/jobs/j1`,
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(queryClient.getQueryCache().find({ queryKey: ['jobs'] })?.state.isInvalidated).toBe(true);
  });
});
