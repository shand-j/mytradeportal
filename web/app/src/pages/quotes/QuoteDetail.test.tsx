import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { QuoteDetail } from './QuoteDetail';
import { createTestQueryClient, resetStores } from '@/test/test-utils';
import * as hooks from '@/lib/api/hooks';
import { mockQuotes } from '@/lib/mock/data/quotes';

const acceptedQuote = mockQuotes.find((q) => q.status === 'accepted')!;
const draftQuote = mockQuotes.find((q) => q.status === 'draft')!;

const deterministicQuote = {
  ...acceptedQuote,
  id: 'quote-deterministic-ui',
  reference: 'Q-DETERMINISTIC-001',
  status: 'draft' as const,
  serviceType: 'BoQ render test',
  propertyAddress: '42 Test Avenue, London',
  lineItems: [
    {
      id: 'line-1',
      description: 'Metal consumer unit 10-way',
      quantity: 2,
      unit: 'item',
      unitPrice: 125,
      total: 250,
      isAiSuggested: false,
    },
    {
      id: 'line-2',
      description: 'Twin & earth cable 2.5mm',
      quantity: 3,
      unit: 'item',
      unitPrice: 48,
      total: 144,
      isAiSuggested: false,
    },
  ],
  subtotal: 394,
  vatAmount: 78.8,
  total: 472.8,
};

const deterministicBoq = {
  id: 'boq-deterministic-ui',
  quoteId: deterministicQuote.id,
  status: 'draft',
  notes: 'Deterministic BoQ for UI rendering test',
  subtotal: 394,
  vatRate: 0.2,
  vatAmount: 78.8,
  total: 472.8,
  confidence: 0.92,
  warnings: [],
  regulatoryCitations: [],
  complianceWarnings: [],
  customerSummaryLines: [
    { description: 'Consumer unit upgrade', total: 250 },
    { description: 'Cabling works', total: 144 },
  ],
  marginIndicator: null,
  standard: 'nrm1',
  suppliers: ['Deterministic Supplier'],
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  lineItems: [
    {
      id: 'boq-line-1',
      code: 'DET-CU-10',
      description: 'Metal consumer unit 10-way',
      category: 'consumer_unit',
      unit: 'each',
      quantity: 2,
      labourHours: 3,
      labourRate: 60,
      labourTotal: 180,
      materialCost: 125,
      materialTotal: 250,
      plantCost: 0,
      plantTotal: 0,
      unitPrice: 125,
      total: 430,
      supplier: 'Deterministic Supplier',
      brand: 'DetBrand',
      sku: 'DET-CU-10',
      productUrl: null,
      retailPriceInclVat: 150,
      notes: null,
    },
  ],
};

const defaultMutation = vi.hoisted(() => () => ({
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
}));

vi.mock('@/lib/api/hooks', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api/hooks')>();
  return {
    ...original,
    useQuote: vi.fn(() => ({ data: acceptedQuote, isLoading: false, error: null })),
    useQuoteBoq: vi.fn(() => ({ data: null, isLoading: false, error: null })),
    useSendQuote: vi.fn(defaultMutation),
    useApproveQuote: vi.fn(defaultMutation),
    useRejectQuote: vi.fn(defaultMutation),
    useConvertQuoteToInvoice: vi.fn(defaultMutation),
    useDeleteQuote: vi.fn(defaultMutation),
    useUpdateQuoteBoq: vi.fn(defaultMutation),
  };
});

function renderQuoteDetail(quoteId: string) {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter initialEntries={[`/quotes/${quoteId}`]}>
        <Routes>
          <Route path="/quotes/:id" element={<QuoteDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('QuoteDetail', () => {
  beforeEach(() => {
    resetStores();
    vi.mocked(hooks.useQuote).mockReturnValue({ data: acceptedQuote, isLoading: false, error: null });
    vi.mocked(hooks.useQuoteBoq).mockReturnValue({ data: null, isLoading: false, error: null });
  });

  it('renders a loading skeleton', () => {
    vi.mocked(hooks.useQuote).mockReturnValue({ data: undefined, isLoading: true, error: null });
    const { container } = renderQuoteDetail(acceptedQuote.id);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders an error message when the quote is missing', () => {
    vi.mocked(hooks.useQuote).mockReturnValue({ data: undefined, isLoading: false, error: new Error('not found') });
    renderQuoteDetail('missing-id');
    expect(screen.getByText(/quote not found/i)).toBeInTheDocument();
  });

  it('renders quote details and line items', () => {
    renderQuoteDetail(acceptedQuote.id);
    expect(screen.getAllByText(acceptedQuote.reference).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(`${acceptedQuote.customer.firstName} ${acceptedQuote.customer.lastName}`)).toBeInTheDocument();
    expect(screen.getByText(/Full property rewire/i)).toBeInTheDocument();
    expect(screen.getByText(/Quote History/i)).toBeInTheDocument();
  });

  it('converts an accepted quote to an invoice', async () => {
    const mutation = defaultMutation();
    vi.mocked(hooks.useConvertQuoteToInvoice).mockReturnValue(mutation as unknown as ReturnType<typeof hooks.useConvertQuoteToInvoice>);

    const user = userEvent.setup();
    renderQuoteDetail(acceptedQuote.id);

    await user.click(screen.getByRole('button', { name: /convert to invoice/i }));
    expect(mutation.mutate).toHaveBeenCalledWith(acceptedQuote.id, expect.any(Object));
  });

  it('sends a draft quote to the customer', async () => {
    vi.mocked(hooks.useQuote).mockReturnValue({ data: draftQuote, isLoading: false, error: null });
    const mutation = defaultMutation();
    vi.mocked(hooks.useSendQuote).mockReturnValue(mutation as unknown as ReturnType<typeof hooks.useSendQuote>);

    const user = userEvent.setup();
    renderQuoteDetail(draftQuote.id);

    await user.click(screen.getByRole('button', { name: /send to customer/i }));
    expect(mutation.mutate).toHaveBeenCalledWith(draftQuote.id, expect.any(Object));
  });

  it('allows editing and saving BoQ line totals', async () => {
    vi.mocked(hooks.useQuoteBoq).mockReturnValue({
      data: {
        id: 'boq-1',
        quoteId: acceptedQuote.id,
        status: 'draft',
        notes: 'Original notes',
        subtotal: 100,
        vatRate: 0.2,
        vatAmount: 20,
        total: 120,
        confidence: 0.9,
        warnings: [],
        regulatoryCitations: [],
        complianceWarnings: [],
        customerSummaryLines: [],
        marginIndicator: null,
        standard: 'nrm1',
        suppliers: ['Screwfix'],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        lineItems: [
          {
            id: 'boq-line-1',
            code: 'EDIT-LINE',
            description: 'Editable BoQ line',
            category: null,
            unit: 'each',
            quantity: 1,
            labourHours: 1,
            labourRate: 10,
            labourTotal: 10,
            materialCost: 50,
            materialTotal: 50,
            plantCost: 0,
            plantTotal: 0,
            unitPrice: 60,
            total: 60,
            supplier: 'Screwfix',
            brand: null,
            sku: null,
            productUrl: null,
            retailPriceInclVat: null,
            notes: null,
          },
        ],
      },
      isLoading: false,
      error: null,
    });
    const boqMutation = defaultMutation();
    vi.mocked(hooks.useUpdateQuoteBoq).mockReturnValue(
      boqMutation as unknown as ReturnType<typeof hooks.useUpdateQuoteBoq>,
    );

    const user = userEvent.setup();
    renderQuoteDetail(acceptedQuote.id);

    await user.click(screen.getByRole('button', { name: /edit boq/i }));

    const labourInput = screen.getByDisplayValue('10');
    await user.clear(labourInput);
    await user.type(labourInput, '12');

    await user.click(screen.getByRole('button', { name: /^save$/i }));
    expect(boqMutation.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ quoteId: acceptedQuote.id }),
      expect.any(Object),
    );
  });

  it('renders deterministic BoQ/line item values and edit/remove controls', async () => {
    vi.mocked(hooks.useQuote).mockReturnValue({ data: deterministicQuote, isLoading: false, error: null });
    vi.mocked(hooks.useQuoteBoq).mockReturnValue({ data: deterministicBoq, isLoading: false, error: null });

    const user = userEvent.setup();
    renderQuoteDetail(deterministicQuote.id);

    expect(screen.getByRole('heading', { name: /quote items/i })).toBeInTheDocument();
    const quoteItemsHeading = screen.getByRole('heading', { name: /quote items/i });
    const quoteItemsTable = quoteItemsHeading.parentElement?.parentElement?.querySelector('table');
    expect(quoteItemsTable).toBeTruthy();

    const quoteTableQueries = within(quoteItemsTable as HTMLTableElement);
    expect(quoteTableQueries.getByRole('columnheader', { name: /^item$/i })).toBeInTheDocument();
    expect(quoteTableQueries.getByRole('columnheader', { name: /^qty$/i })).toBeInTheDocument();
    expect(quoteTableQueries.getByRole('columnheader', { name: /unit price/i })).toBeInTheDocument();
    expect(quoteTableQueries.getByRole('columnheader', { name: /^total$/i })).toBeInTheDocument();

    expect(quoteTableQueries.getByText('Metal consumer unit 10-way')).toBeInTheDocument();
    expect(quoteTableQueries.getByText('2 item')).toBeInTheDocument();
    expect(quoteTableQueries.getByText('£125.00')).toBeInTheDocument();
    expect(quoteTableQueries.getByText('£250.00')).toBeInTheDocument();

    expect(screen.getByRole('heading', { name: /bill of quantities/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /^labour$/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /^materials$/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /edit quote/i }));
    expect(screen.getAllByRole('button', { name: /remove/i }).length).toBeGreaterThan(0);
  });
});
