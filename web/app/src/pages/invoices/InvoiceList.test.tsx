import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { InvoiceList } from './InvoiceList';
import { useInvoices, useContacts } from '@/lib/api/hooks';
import { renderPage, resetStores } from '@/test/test-utils';
import { mockInvoices } from '@/lib/mock/data/invoices';
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
    useInvoices: vi.fn(() => ({ data: undefined, isLoading: true, error: null })),
    useContacts: vi.fn(() => ({ data: [], isLoading: false, error: null })),
    useCreateInvoice: vi.fn(() => defaultMutations),
    useSendInvoice: vi.fn(() => defaultMutations),
  };
});

describe('InvoiceList', () => {
  beforeEach(() => {
    resetStores();
    vi.mocked(useInvoices).mockReturnValue({ data: mockInvoices, isLoading: false, error: null });
    vi.mocked(useContacts).mockReturnValue({ data: mockCustomers, isLoading: false, error: null });
  });

  it('renders a loading skeleton', () => {
    vi.mocked(useInvoices).mockReturnValue({ data: undefined, isLoading: true, error: null });
    const { container } = renderPage(<InvoiceList />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders an error message', () => {
    vi.mocked(useInvoices).mockReturnValue({ data: undefined, isLoading: false, error: new Error('boom') });
    renderPage(<InvoiceList />);
    expect(screen.getByText('Failed to load invoices')).toBeInTheDocument();
  });

  it('renders invoices from mock data', () => {
    renderPage(<InvoiceList />);
    expect(screen.getByText('Invoices')).toBeInTheDocument();
    expect(screen.getByText('INV-2025-0089')).toBeInTheDocument();
    expect(screen.getByText('Total Paid')).toBeInTheDocument();
  });

  it('filters invoices by status', async () => {
    const user = userEvent.setup();
    renderPage(<InvoiceList />);

    const statusSelect = screen.getByDisplayValue('All Status');
    await user.selectOptions(statusSelect, 'overdue');

    expect(screen.getByText('INV-2025-0086')).toBeInTheDocument();
    expect(screen.queryByText('INV-2025-0089')).not.toBeInTheDocument();
  });
});
