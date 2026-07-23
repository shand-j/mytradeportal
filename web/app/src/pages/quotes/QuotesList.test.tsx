import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { QuotesList } from './QuotesList';
import { useQuotes, useContacts } from '@/lib/api/hooks';
import { renderPage, resetStores } from '@/test/test-utils';
import { mockQuotes } from '@/lib/mock/data/quotes';
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
    useQuotes: vi.fn(() => ({ data: undefined, isLoading: true, error: null })),
    useContacts: vi.fn(() => ({ data: [], isLoading: false, error: null })),
    useCreateQuote: vi.fn(() => defaultMutations),
    useSendQuote: vi.fn(() => defaultMutations),
    useRejectQuote: vi.fn(() => defaultMutations),
    useDeleteQuote: vi.fn(() => defaultMutations),
    useGenerateQuote: vi.fn(() => defaultMutations),
  };
});

describe('QuotesList', () => {
  beforeEach(() => {
    resetStores();
    vi.mocked(useQuotes).mockReturnValue({ data: mockQuotes, isLoading: false, error: null });
    vi.mocked(useContacts).mockReturnValue({ data: mockCustomers, isLoading: false, error: null });
  });

  it('renders a loading skeleton', () => {
    vi.mocked(useQuotes).mockReturnValue({ data: undefined, isLoading: true, error: null });
    const { container } = renderPage(<QuotesList />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders an error message', () => {
    vi.mocked(useQuotes).mockReturnValue({ data: undefined, isLoading: false, error: new Error('boom') });
    renderPage(<QuotesList />);
    expect(screen.getByText('Failed to load quotes')).toBeInTheDocument();
  });

  it('renders quotes from mock data', () => {
    renderPage(<QuotesList />);
    expect(screen.getByText('Quotes')).toBeInTheDocument();
    expect(screen.getByText('Q-2025-0042')).toBeInTheDocument();
    expect(screen.getByText('Full Rewire')).toBeInTheDocument();
  });

  it('filters quotes by search term', async () => {
    const user = userEvent.setup();
    renderPage(<QuotesList />);

    const searchInput = screen.getByPlaceholderText(/search quotes or customers/i);
    await user.type(searchInput, 'EV');

    expect(screen.getByText('EV Charger Installation')).toBeInTheDocument();
    expect(screen.queryByText('Full Rewire')).not.toBeInTheDocument();
  });
});
