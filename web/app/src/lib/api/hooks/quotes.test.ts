import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { waitFor } from '@testing-library/react';

import {
  useQuotes,
  useQuote,
  useCreateQuote,
  useSendQuote,
  useUpdateQuote,
  useDeleteQuote,
  useGenerateQuote,
  useRefineQuote,
  useConvertQuoteToInvoice,
} from './quotes';
import { renderHookWithProviders, createTestQueryClient } from '@/test/test-utils';
import type { Quote } from '@/types';

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

function mockQuoteResponse(id: string, overrides: Record<string, unknown> = {}) {
  return buildResponse({
    id,
    reference: `Q-${id}`,
    customer_id: 'c1',
    status: 'draft',
    line_items: [],
    subtotal: 0,
    vat_amount: 0,
    vat_rate: 20,
    total: 0,
    ai_generated: false,
    ai_confidence: null,
    ai_warnings: [],
    ai_assumptions: [],
    ai_notes: null,
    retrieval_status: null,
    service_type: 'Test',
    property_address: '',
    customer_message: null,
    internal_notes: null,
    expires_at: null,
    accepted_at: null,
    sent_at: null,
    created_at: '2025-01-01T00:00:00Z',
    ...overrides,
  });
}

function renderHookNoAuth<TProps, TResult>(hook: (props: TProps) => TResult) {
  return renderHookWithProviders(hook, { withAuth: false });
}

describe('quote hooks', () => {
  beforeEach(() => {
    globalThis.fetch = mockFetch as unknown as typeof fetch;
    vi.stubEnv('VITE_API_BASE_URL', API_BASE_URL);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    mockFetch.mockClear();
  });

  it('useQuotes fetches and camelizes the list', async () => {
    mockFetch.mockResolvedValueOnce(
      buildResponse([
        {
          id: 'q1',
          reference: 'Q-1',
          customer_id: 'c1',
          status: 'draft',
          line_items: [],
          subtotal: 100,
          vat_amount: 20,
          vat_rate: 20,
          total: 120,
          ai_generated: false,
          ai_confidence: null,
          ai_warnings: [],
          ai_assumptions: [],
          ai_notes: null,
          retrieval_status: null,
          service_type: 'Test',
          property_address: '1 Road',
          customer_message: null,
          internal_notes: null,
          expires_at: null,
          accepted_at: null,
          sent_at: null,
          created_at: '2025-01-01T00:00:00Z',
        },
      ]),
    );

    const { result } = renderHookNoAuth(() => useQuotes());

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/quotes`,
      expect.objectContaining({ method: 'GET', credentials: 'include' }),
    );

    const data = result.current.data as Quote[];
    expect(data).toHaveLength(1);
    expect(data[0].customerId).toBe('c1');
    expect(data[0].propertyAddress).toBe('1 Road');
  });

  it('useQuote fetches a single quote when an id is provided', async () => {
    mockFetch.mockResolvedValueOnce(mockQuoteResponse('q1', { status: 'sent' }));

    const { result } = renderHookNoAuth(() => useQuote('q1'));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/quotes/q1`,
      expect.objectContaining({ method: 'GET' }),
    );
    expect((result.current.data as Quote).status).toBe('sent');
  });

  it('useQuote does not fetch when the id is empty', () => {
    renderHookNoAuth(() => useQuote(''));
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('useQuotes surfaces an ApiError on failure', async () => {
    mockFetch.mockResolvedValueOnce(buildResponse({ detail: 'boom' }, 500));

    const { result } = renderHookNoAuth(() => useQuotes());

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('boom');
  });

  it('useCreateQuote posts a decamelized body and invalidates the list key', async () => {
    mockFetch.mockResolvedValueOnce(mockQuoteResponse('q-new'));

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['quotes'], []);

    const { result } = renderHookWithProviders(() => useCreateQuote(), { queryClient, withAuth: false });

    await result.current.mutateAsync({
      customerId: 'c1',
      reference: 'Q-NEW',
      serviceType: 'Test',
      propertyAddress: '1 Road',
      status: 'draft',
      lineItems: [],
      subtotal: 0,
      vatRate: 20,
      vatAmount: 0,
      total: 0,
      aiGenerated: false,
      aiConfidence: null,
      aiWarnings: [],
      aiAssumptions: [],
      aiNotes: null,
      retrievalStatus: null,
      customerMessage: null,
      internalNotes: null,
      expiresAt: null,
    });

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/quotes`,
      expect.objectContaining({ method: 'POST' }),
    );

    const body = lastFetchBody();
    expect(body).toHaveProperty('contact_id', 'c1');
    expect(body).toHaveProperty('title', 'Q-NEW');
    expect(body).toHaveProperty('description', 'Test - 1 Road');

    expect(queryClient.getQueryCache().find({ queryKey: ['quotes'] })?.state.isInvalidated).toBe(true);
  });

  it('useSendQuote posts to /quotes/:id/send and invalidates detail key', async () => {
    mockFetch.mockResolvedValueOnce(mockQuoteResponse('q1', { status: 'sent' }));

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['quotes'], []);
    queryClient.setQueryData(['quote', 'q1'], {});

    const { result } = renderHookWithProviders(() => useSendQuote(), { queryClient, withAuth: false });

    await result.current.mutateAsync('q1');

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/quotes/q1/send`,
      expect.objectContaining({ method: 'POST' }),
    );

    expect(queryClient.getQueryCache().find({ queryKey: ['quotes'] })?.state.isInvalidated).toBe(true);
    expect(queryClient.getQueryCache().find({ queryKey: ['quote', 'q1'] })?.state.isInvalidated).toBe(true);
  });

  it('useUpdateQuote patches a quote and invalidates both keys', async () => {
    mockFetch.mockResolvedValueOnce(mockQuoteResponse('q1'));

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['quotes'], []);
    queryClient.setQueryData(['quote', 'q1'], {});

    const { result } = renderHookWithProviders(() => useUpdateQuote(), { queryClient, withAuth: false });

    await result.current.mutateAsync({ id: 'q1', data: { status: 'sent' } as Partial<Quote> });

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/quotes/q1`,
      expect.objectContaining({ method: 'PATCH' }),
    );

    expect(lastFetchBody()).toHaveProperty('status', 'sent');

    expect(queryClient.getQueryCache().find({ queryKey: ['quote', 'q1'] })?.state.isInvalidated).toBe(true);
    expect(queryClient.getQueryCache().find({ queryKey: ['quotes'] })?.state.isInvalidated).toBe(true);
  });

  it('useDeleteQuote deletes a quote and invalidates the list key', async () => {
    mockFetch.mockResolvedValueOnce(buildResponse(null, 204));

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['quotes'], []);

    const { result } = renderHookWithProviders(() => useDeleteQuote(), { queryClient, withAuth: false });

    await result.current.mutateAsync('q1');

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/quotes/q1`,
      expect.objectContaining({ method: 'DELETE' }),
    );

    expect(queryClient.getQueryCache().find({ queryKey: ['quotes'] })?.state.isInvalidated).toBe(true);
  });

  it('useGenerateQuote posts generation variables and invalidates contacts when a contactId is used', async () => {
    mockFetch.mockResolvedValueOnce(mockQuoteResponse('q-ai', { ai_generated: true, ai_confidence: 0.95, service_type: 'AI Test' }));

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['quotes'], []);
    queryClient.setQueryData(['contacts'], []);

    const { result } = renderHookWithProviders(() => useGenerateQuote(), { queryClient, withAuth: false });

    await result.current.mutateAsync({
      contactId: 'c1',
      description: 'Full rewire',
      propertyType: 'house',
    });

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/quotes/generate`,
      expect.objectContaining({ method: 'POST' }),
    );

    const body = lastFetchBody();
    expect(body).toHaveProperty('contact_id', 'c1');

    expect(queryClient.getQueryCache().find({ queryKey: ['quotes'] })?.state.isInvalidated).toBe(true);
    expect(queryClient.getQueryCache().find({ queryKey: ['contacts'] })?.state.isInvalidated).toBe(true);
  });

  it('useRefineQuote posts instructions and invalidates detail key', async () => {
    mockFetch.mockResolvedValueOnce(mockQuoteResponse('q1'));

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['quote', 'q1'], {});

    const { result } = renderHookWithProviders(() => useRefineQuote(), { queryClient, withAuth: false });

    await result.current.mutateAsync({ id: 'q1', instructions: 'Add more sockets' });

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/quotes/q1/refine`,
      expect.objectContaining({ method: 'POST' }),
    );

    expect(lastFetchBody()).toHaveProperty('instructions', 'Add more sockets');
    expect(queryClient.getQueryCache().find({ queryKey: ['quote', 'q1'] })?.state.isInvalidated).toBe(true);
  });

  it('useConvertQuoteToInvoice posts and invalidates quote and invoice keys', async () => {
    mockFetch.mockResolvedValueOnce(buildResponse({
      id: 'inv-1', reference: 'INV-1', customer_id: 'c1', status: 'draft', line_items: [],
      subtotal: 0, vat_amount: 0, vat_rate: 20, total: 0, amount_paid: 0, amount_due: 0,
      issue_date: '2025-01-01', due_date: '2025-01-15', paid_at: null, payment_method: null,
      created_at: '2025-01-01T00:00:00Z',
    }));

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['quotes'], []);
    queryClient.setQueryData(['quote', 'q1'], {});
    queryClient.setQueryData(['invoices'], []);

    const { result } = renderHookWithProviders(() => useConvertQuoteToInvoice(), { queryClient, withAuth: false });

    await result.current.mutateAsync('q1');

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/quotes/q1/convert-to-invoice`,
      expect.objectContaining({ method: 'POST' }),
    );

    expect(queryClient.getQueryCache().find({ queryKey: ['quote', 'q1'] })?.state.isInvalidated).toBe(true);
    expect(queryClient.getQueryCache().find({ queryKey: ['quotes'] })?.state.isInvalidated).toBe(true);
    expect(queryClient.getQueryCache().find({ queryKey: ['invoices'] })?.state.isInvalidated).toBe(true);
  });

  it('maps the AI quote fields from the snake_case API response', async () => {
    mockFetch.mockResolvedValueOnce(
      mockQuoteResponse('q-ai', {
        ai_generated: true,
        ai_confidence: 0.87,
        ai_warnings: ['Price above typical range'],
        ai_assumptions: ['Standard 3-bed layout'],
        ai_notes: 'Review consumer unit brand with customer',
        retrieval_status: 'no_index',
        line_items: [
          {
            id: 'li-1',
            description: 'Consumer unit',
            quantity: 1,
            unit_price: 480,
            total: 480,
            ai_generated: true,
          },
        ],
      }),
    );

    const { result } = renderHookNoAuth(() => useQuote('q-ai'));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const quote = result.current.data as Quote;
    expect(quote.aiGenerated).toBe(true);
    expect(quote.aiConfidence).toBe(0.87);
    expect(quote.aiWarnings).toEqual(['Price above typical range']);
    expect(quote.aiAssumptions).toEqual(['Standard 3-bed layout']);
    expect(quote.aiNotes).toBe('Review consumer unit brand with customer');
    expect(quote.retrievalStatus).toBe('no_index');
    expect(quote.lineItems[0].aiGenerated).toBe(true);
  });

  it('defaults the AI quote fields when the API omits them', async () => {
    mockFetch.mockResolvedValueOnce(buildResponse({
      id: 'q-plain',
      reference: 'Q-PLAIN',
      customer_id: 'c1',
      status: 'draft',
      line_items: [{ id: 'li-1', description: 'Labour', quantity: 1, unit_price: 100 }],
      subtotal: 100,
      vat_amount: 20,
      vat_rate: 20,
      total: 120,
      service_type: 'Test',
      created_at: '2025-01-01T00:00:00Z',
    }));

    const { result } = renderHookNoAuth(() => useQuote('q-plain'));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const quote = result.current.data as Quote;
    expect(quote.aiGenerated).toBe(false);
    expect(quote.aiConfidence).toBeNull();
    expect(quote.aiWarnings).toEqual([]);
    expect(quote.aiAssumptions).toEqual([]);
    expect(quote.aiNotes).toBeNull();
    expect(quote.retrievalStatus).toBeNull();
    expect(quote.lineItems[0].aiGenerated).toBe(false);
  });
});
