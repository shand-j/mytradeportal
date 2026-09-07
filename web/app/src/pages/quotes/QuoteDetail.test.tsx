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
  serviceType: 'AI panel render test',
  propertyAddress: '42 Test Avenue, London',
  aiGenerated: true,
  aiConfidence: 0.87,
  aiWarnings: ['Price above typical range for consumer units'],
  aiAssumptions: ['Standard 3-bed layout'],
  aiNotes: 'Confirm cable routes on site',
  retrievalStatus: 'no_index' as const,
  lineItems: [
    {
      id: 'line-1',
      description: 'Metal consumer unit 10-way',
      quantity: 2,
      unit: 'item',
      unitPrice: 125,
      total: 250,
      aiGenerated: true,
      isAiSuggested: true,
    },
    {
      id: 'line-2',
      description: 'Twin & earth cable 2.5mm',
      quantity: 3,
      unit: 'item',
      unitPrice: 48,
      total: 144,
      aiGenerated: false,
      isAiSuggested: false,
    },
  ],
  subtotal: 394,
  vatAmount: 78.8,
  total: 472.8,
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
    useSendQuote: vi.fn(defaultMutation),
    useApproveQuote: vi.fn(defaultMutation),
    useRejectQuote: vi.fn(defaultMutation),
    useConvertQuoteToInvoice: vi.fn(defaultMutation),
    useDeleteQuote: vi.fn(defaultMutation),
    useRefineQuote: vi.fn(defaultMutation),
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

  it('hides the AI panel for non-AI quotes', () => {
    const manualQuote = mockQuotes.find((q) => !q.aiGenerated)!;
    vi.mocked(hooks.useQuote).mockReturnValue({ data: manualQuote, isLoading: false, error: null });
    renderQuoteDetail(manualQuote.id);
    expect(screen.queryByText(/review before sending/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /refine quote/i })).not.toBeInTheDocument();
  });

  it('renders the AI panel with confidence, warnings, assumptions and notes', () => {
    vi.mocked(hooks.useQuote).mockReturnValue({ data: deterministicQuote, isLoading: false, error: null });
    renderQuoteDetail(deterministicQuote.id);

    expect(screen.getByText(/review before sending/i)).toBeInTheDocument();
    expect(screen.getByText('87%')).toBeInTheDocument();
    expect(screen.getByText(/no catalogue match/i)).toBeInTheDocument();
    expect(screen.getByText(/Price above typical range/i)).toBeInTheDocument();
    expect(screen.getByText(/Standard 3-bed layout/i)).toBeInTheDocument();
    expect(screen.getByText(/Confirm cable routes on site/i)).toBeInTheDocument();
  });

  it('marks AI-suggested line items with a sparkle indicator', () => {
    vi.mocked(hooks.useQuote).mockReturnValue({ data: deterministicQuote, isLoading: false, error: null });
    renderQuoteDetail(deterministicQuote.id);

    const quoteItemsHeading = screen.getByRole('heading', { name: /quote items/i });
    const quoteItemsTable = quoteItemsHeading.parentElement?.parentElement?.querySelector('table');
    expect(quoteItemsTable).toBeTruthy();

    const quoteTableQueries = within(quoteItemsTable as HTMLTableElement);
    expect(quoteTableQueries.getAllByLabelText(/ai suggested line/i)).toHaveLength(1);
  });

  it('refines an AI quote with instructions', async () => {
    vi.mocked(hooks.useQuote).mockReturnValue({ data: deterministicQuote, isLoading: false, error: null });
    const mutation = defaultMutation();
    vi.mocked(hooks.useRefineQuote).mockReturnValue(mutation as unknown as ReturnType<typeof hooks.useRefineQuote>);

    const user = userEvent.setup();
    renderQuoteDetail(deterministicQuote.id);

    const refineButton = screen.getByRole('button', { name: /refine quote/i });
    expect(refineButton).toBeDisabled();

    await user.type(screen.getByLabelText(/refine with ai/i), 'Add 2 more sockets');
    await user.click(screen.getByRole('button', { name: /refine quote/i }));

    expect(mutation.mutate).toHaveBeenCalledWith(
      { id: deterministicQuote.id, instructions: 'Add 2 more sockets' },
      expect.any(Object),
    );
  });

  it('renders deterministic line item values and edit/remove controls', async () => {
    vi.mocked(hooks.useQuote).mockReturnValue({ data: deterministicQuote, isLoading: false, error: null });

    const user = userEvent.setup();
    renderQuoteDetail(deterministicQuote.id);

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

    await user.click(screen.getByRole('button', { name: /edit quote/i }));
    expect(screen.getAllByRole('button', { name: /remove/i }).length).toBeGreaterThan(0);
  });
});
