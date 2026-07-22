import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { CustomerDirectory } from './CustomerDirectory';
import { useContacts, useCreateContact, useDeleteContact } from '@/lib/api/hooks';
import { renderPage, resetStores } from '@/test/test-utils';
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
    useContacts: vi.fn(() => ({ data: undefined, isLoading: true, error: null })),
    useCreateContact: vi.fn(() => defaultMutations),
    useDeleteContact: vi.fn(() => defaultMutations),
  };
});

describe('CustomerDirectory', () => {
  beforeEach(() => {
    resetStores();
    vi.mocked(useContacts).mockReturnValue({ data: mockCustomers, isLoading: false, error: null });
    vi.mocked(useCreateContact).mockReturnValue(defaultMutations);
    vi.mocked(useDeleteContact).mockReturnValue(defaultMutations);
  });

  it('renders a loading skeleton', () => {
    vi.mocked(useContacts).mockReturnValue({ data: undefined, isLoading: true, error: null });
    const { container } = renderPage(<CustomerDirectory />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders an error message', () => {
    vi.mocked(useContacts).mockReturnValue({ data: undefined, isLoading: false, error: new Error('boom') });
    renderPage(<CustomerDirectory />);
    expect(screen.getByText('Failed to load customers')).toBeInTheDocument();
  });

  it('renders customer cards from mock data', () => {
    renderPage(<CustomerDirectory />);
    expect(screen.getByText('Customers')).toBeInTheDocument();
    expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
    expect(screen.getByText('David Smith')).toBeInTheDocument();
  });

  it('filters customers by search term', async () => {
    const user = userEvent.setup();
    renderPage(<CustomerDirectory />);

    const searchInput = screen.getByPlaceholderText(/search customers/i);
    await user.type(searchInput, 'Emma');

    expect(screen.getByText('Emma Wilson')).toBeInTheDocument();
    expect(screen.queryByText('Sarah Johnson')).not.toBeInTheDocument();
  });
});
