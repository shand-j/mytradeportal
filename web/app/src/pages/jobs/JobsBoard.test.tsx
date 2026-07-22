import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { JobsBoard } from './JobsBoard';
import { useJobs, useContacts, useCreateJob, useTransitionJobStatus } from '@/lib/api/hooks';
import { renderPage, resetStores } from '@/test/test-utils';
import { mockJobs } from '@/lib/mock/data/jobs';
import { mockCustomers } from '@/lib/mock/data/customers';

const defaultMutations = {
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  isPending: false,
  isIdle: true,
  isSuccess: false,
  isError: false,
  reset: vi.fn(),
  error: null,
  data: undefined,
  status: 'idle',
  failureCount: 0,
  failureReason: null,
  submittedAt: 0,
};

vi.mock('@/lib/api/hooks', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api/hooks')>();
  return {
    ...original,
    useJobs: vi.fn(() => ({ data: undefined, isLoading: true, error: null })),
    useContacts: vi.fn(() => ({ data: [], isLoading: false, error: null })),
    useCreateJob: vi.fn(() => defaultMutations),
    useTransitionJobStatus: vi.fn(() => defaultMutations),
  };
});

describe('JobsBoard', () => {
  beforeEach(() => {
    resetStores();
    vi.mocked(useJobs).mockReturnValue({ data: mockJobs, isLoading: false, error: null });
    vi.mocked(useContacts).mockReturnValue({ data: mockCustomers, isLoading: false, error: null });
    vi.mocked(useCreateJob).mockReturnValue(defaultMutations);
    vi.mocked(useTransitionJobStatus).mockReturnValue(defaultMutations);
  });

  it('renders a loading skeleton', () => {
    vi.mocked(useJobs).mockReturnValue({ data: undefined, isLoading: true, error: null });
    const { container } = renderPage(<JobsBoard />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders an error message', () => {
    vi.mocked(useJobs).mockReturnValue({ data: undefined, isLoading: false, error: new Error('boom') });
    renderPage(<JobsBoard />);
    expect(screen.getByText('Failed to load jobs')).toBeInTheDocument();
  });

  it('renders job board columns from mock data', () => {
    renderPage(<JobsBoard />);
    expect(screen.getByText('Jobs')).toBeInTheDocument();
    expect(screen.getByText('Scheduled')).toBeInTheDocument();
    expect(screen.getByText('In Progress')).toBeInTheDocument();
    expect(screen.getByText('Smart Home Installation')).toBeInTheDocument();
  });

  it('filters jobs by search term', async () => {
    const user = userEvent.setup();
    renderPage(<JobsBoard />);

    const searchInput = screen.getByPlaceholderText(/search jobs/i);
    await user.type(searchInput, 'Solar');

    expect(screen.getByText('Solar PV Installation')).toBeInTheDocument();
    expect(screen.queryByText('Smart Home Installation')).not.toBeInTheDocument();
  });
});
