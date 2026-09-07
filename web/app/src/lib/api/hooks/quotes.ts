import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { BillOfQuantities, BoQLineItem, Customer, Invoice, Quote, QuoteLineItem } from '@/types';

const quoteKeys = {
  all: ['quotes'] as const,
  detail: (id: string) => ['quote', id] as const,
};

import { toCustomer } from './contacts';

function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : fallback;
  }
  if (typeof value === 'string') {
    const normalized = value.replaceAll(',', '').trim();
    if (!normalized) return fallback;
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

function toCustomerSummaryLine(raw: Record<string, unknown>) {
  return {
    description: String(raw.description ?? ''),
    total: Number(raw.total ?? 0),
  };
}

function toMarginIndicator(raw: Record<string, unknown> | null | undefined) {
  if (!raw) return null;
  return {
    materialSubtotal: Number(raw.materialSubtotal ?? 0),
    labourSubtotal: Number(raw.labourSubtotal ?? 0),
    subtotal: Number(raw.subtotal ?? 0),
    targetMarkupPercent: Number(raw.targetMarkupPercent ?? 0),
    estimatedMarginPercent: Number(raw.estimatedMarginPercent ?? 0),
    estimatedMarginAmount: Number(raw.estimatedMarginAmount ?? 0),
  };
}

function normalizeQuoteStatus(status: string): Quote['status'] {
  // The backend uses "approved"; the UI uses "accepted".
  if (status === 'approved') return 'accepted';
  if (
    status === 'draft' ||
    status === 'sent' ||
    status === 'accepted' ||
    status === 'rejected' ||
    status === 'expired'
  ) {
    return status;
  }
  return 'draft';
}

function toLineItem(raw: Record<string, unknown>): QuoteLineItem {
  const quantity = Number(raw.quantity ?? 1);
  const unitPrice = Number(raw.unitPrice ?? 0);
  const total = raw.total != null ? Number(raw.total) : quantity * unitPrice;
  return {
    id: String(raw.id),
    description: String(raw.description ?? ''),
    quantity,
    unit: (raw.unit as string) ?? 'item',
    unitPrice,
    total,
    aiGenerated: Boolean(raw.aiGenerated ?? raw.isAiSuggested ?? false),
    isAiSuggested: Boolean(raw.isAiSuggested ?? raw.aiGenerated ?? false),
  };
}

function toBoQLineItem(raw: Record<string, unknown>): BoQLineItem {
  const quantity = toNumber(raw.quantity, 1);
  const labourTotal = toNumber(raw.labourTotal ?? raw.labour, 0);
  const materialTotal = toNumber(raw.materialTotal ?? raw.materials, 0);
  const plantTotal = toNumber(raw.plantTotal ?? raw.plant, 0);
  const unitPrice = toNumber(raw.unitPrice, 0);
  const total = toNumber(raw.total, labourTotal + materialTotal + plantTotal || quantity * unitPrice);

  return {
    id: String(raw.id),
    code: String(raw.code ?? ''),
    description: String(raw.description ?? ''),
    category: (raw.category as string | null) ?? null,
    unit: String(raw.unit ?? 'item'),
    quantity,
    labourHours: toNumber(raw.labourHours, 0),
    labourRate: toNumber(raw.labourRate, 0),
    labourTotal,
    materialCost: toNumber(raw.materialCost, 0),
    materialTotal,
    plantCost: toNumber(raw.plantCost, 0),
    plantTotal,
    unitPrice,
    total,
    supplier: (raw.supplier as string | null) ?? null,
    brand: (raw.brand as string | null) ?? null,
    sku: (raw.sku as string | null) ?? null,
    productUrl: (raw.productUrl as string | null) ?? null,
    retailPriceInclVat: raw.retailPriceInclVat != null ? toNumber(raw.retailPriceInclVat, 0) : null,
    notes: (raw.notes as string | null) ?? null,
  };
}

function toBillOfQuantities(raw: Record<string, unknown>): BillOfQuantities {
  const lineItems = Array.isArray(raw.lineItems)
    ? raw.lineItems.map((item) => toBoQLineItem(item as Record<string, unknown>))
    : [];
  const suppliers = Array.from(
    new Set(lineItems.map((item) => item.supplier).filter(Boolean))
  ) as string[];
  return {
    id: String(raw.id),
    quoteId: String(raw.quoteId),
    status: String(raw.status ?? 'draft'),
    notes: (raw.notes as string | null) ?? null,
    subtotal: Number(raw.subtotal ?? 0),
    vatRate: Number(raw.vatRate ?? 0.2),
    vatAmount: Number(raw.vatAmount ?? 0),
    total: Number(raw.total ?? 0),
    confidence: Number(raw.confidence ?? 0),
    warnings: Array.isArray(raw.warnings) ? raw.warnings.map(String) : [],
    regulatoryCitations: Array.isArray(raw.regulatoryCitations)
      ? (raw.regulatoryCitations as Array<Record<string, unknown>>)
      : [],
    complianceWarnings: Array.isArray(raw.complianceWarnings)
      ? raw.complianceWarnings.map(String)
      : [],
    customerSummaryLines: Array.isArray(raw.customerSummaryLines)
      ? raw.customerSummaryLines.map((line) => toCustomerSummaryLine(line as Record<string, unknown>))
      : [],
    marginIndicator: toMarginIndicator((raw.marginIndicator as Record<string, unknown>) ?? null),
    standard: (raw.standard as string | null) ?? null,
    lineItems,
    suppliers,
    createdAt: String(raw.createdAt),
    updatedAt: String(raw.updatedAt),
  };
}

export function toQuote(raw: Record<string, unknown>): Quote {
  const customer = raw.customer ? toCustomer(raw.customer as Record<string, unknown>) : undefined;
  return {
    id: String(raw.id),
    reference: (raw.reference as string) ?? (raw.title as string) ?? `Q-${String(raw.id).slice(0, 8)}`,
    customerId: String(raw.customerId ?? raw.contactId ?? ''),
    customer: customer as Customer,
    status: normalizeQuoteStatus(String(raw.status)),
    lineItems: Array.isArray(raw.lineItems) ? raw.lineItems.map((item) => toLineItem(item as Record<string, unknown>)) : [],
    billOfQuantities: raw.billOfQuantities
      ? toBillOfQuantities(raw.billOfQuantities as Record<string, unknown>)
      : null,
    subtotal: Number(raw.subtotal ?? 0),
    vatAmount: Number(raw.vatAmount ?? 0),
    vatRate: Number(raw.vatRate ?? 0.2),
    total: Number(raw.total ?? 0),
    aiGenerated: Boolean(raw.aiGenerated ?? false),
    aiConfidence: raw.aiConfidence != null ? Number(raw.aiConfidence) : null,
    aiWarnings: Array.isArray(raw.aiWarnings) ? raw.aiWarnings.map(String) : [],
    aiAssumptions: Array.isArray(raw.aiAssumptions) ? raw.aiAssumptions.map(String) : [],
    aiNotes: (raw.aiNotes as string | null) ?? null,
    retrievalStatus: (raw.retrievalStatus as Quote['retrievalStatus']) ?? null,
    serviceType: (raw.serviceType as string) ?? (raw.title as string) ?? '',
    propertyAddress: (raw.propertyAddress as string) ?? '',
    customerMessage: (raw.customerMessage as string | null) ?? null,
    internalNotes: (raw.internalNotes as string | null) ?? null,
    expiresAt: (raw.expiresAt as string | null) ?? (raw.validUntil as string | null) ?? null,
    acceptedAt: (raw.acceptedAt as string | null) ?? (raw.approvedAt as string | null) ?? null,
    sentAt: (raw.sentAt as string | null) ?? null,
    createdAt: String(raw.createdAt),
  };
}

const invoiceKeys = {
  all: ['invoices'] as const,
};

export function useQuotes() {
  return useQuery<Quote[], ApiError>({
    queryKey: quoteKeys.all,
    queryFn: async () => {
      const data = await api.get<Record<string, unknown>[]>('/quotes');
      return data.map(toQuote);
    },
  });
}

export function useQuote(id: string) {
  return useQuery<Quote, ApiError>({
    queryKey: quoteKeys.detail(id),
    queryFn: async () => {
      const data = await api.get<Record<string, unknown>>(`/quotes/${id}`);
      return toQuote(data);
    },
    enabled: Boolean(id),
  });
}

export type CreateQuotePayload = Omit<
  Quote,
  'id' | 'createdAt' | 'sentAt' | 'acceptedAt' | 'customer' | 'billOfQuantities'
> & {
  customerId: string;
};

function toBackendQuoteCreate(data: CreateQuotePayload): Record<string, unknown> {
  return {
    contact_id: data.customerId,
    title: data.reference,
    description: [data.serviceType, data.propertyAddress].filter(Boolean).join(' - ') || null,
    line_items: data.lineItems.map(({ description, quantity, unitPrice }) => ({
      description,
      quantity,
      unit_price: unitPrice,
    })),
  };
}

export function useCreateQuote() {
  const queryClient = useQueryClient();

  return useMutation<Quote, ApiError, CreateQuotePayload>({
    mutationFn: async (data) => {
      const raw = await api.post<Record<string, unknown>>('/quotes', toBackendQuoteCreate(data));
      return toQuote(raw);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.all });
    },
  });
}

function toBackendQuoteUpdate(data: Partial<Quote>): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  if ('reference' in data && data.reference != null) payload.title = data.reference;
  if ('serviceType' in data || 'propertyAddress' in data) {
    payload.description = [data.serviceType, data.propertyAddress].filter(Boolean).join(' - ') || null;
  }
  if ('lineItems' in data && data.lineItems != null) {
    payload.line_items = data.lineItems.map(({ description, quantity, unitPrice }) => ({
      description,
      quantity,
      unit_price: unitPrice,
    }));
  }
  if ('status' in data && data.status != null) {
    payload.status = data.status === 'accepted' ? 'approved' : data.status;
  }
  return payload;
}

export function useUpdateQuote() {
  const queryClient = useQueryClient();

  return useMutation<Quote, ApiError, { id: string; data: Partial<Quote> }>({
    mutationFn: async ({ id, data }) => {
      const raw = await api.patch<Record<string, unknown>>(`/quotes/${id}`, toBackendQuoteUpdate(data));
      return toQuote(raw);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.all });
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(variables.id) });
    },
  });
}

export function useSendQuote() {
  const queryClient = useQueryClient();

  return useMutation<Quote, ApiError, string>({
    mutationFn: async (id) => {
      const raw = await api.post<Record<string, unknown>>(`/quotes/${id}/send`);
      return toQuote(raw);
    },
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.all });
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(id) });
    },
  });
}

export function useApproveQuote() {
  const queryClient = useQueryClient();

  return useMutation<Quote, ApiError, string>({
    mutationFn: async (id) => {
      const raw = await api.post<Record<string, unknown>>(`/quotes/${id}/approve`, { approved: true });
      return toQuote(raw);
    },
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.all });
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(id) });
    },
  });
}

export function useRejectQuote() {
  const queryClient = useQueryClient();

  return useMutation<Quote, ApiError, string>({
    mutationFn: async (id) => {
      const raw = await api.post<Record<string, unknown>>(`/quotes/${id}/reject`);
      return toQuote(raw);
    },
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.all });
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(id) });
    },
  });
}

export interface GenerateQuoteVariables {
  contactId?: string;
  customerName?: string;
  customerEmail?: string;
  customerPhone?: string;
  description: string;
  propertyType?: string;
}

export function useGenerateQuote() {
  const queryClient = useQueryClient();

  return useMutation<Quote, ApiError, GenerateQuoteVariables>({
    mutationFn: async (data) => {
      const raw = await api.post<Record<string, unknown>>('/quotes/generate', data);
      return toQuote(raw);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.all });
      if (variables.contactId) {
        queryClient.invalidateQueries({ queryKey: ['contacts'] });
      }
    },
  });
}

export interface RefineQuoteVariables {
  id: string;
  instructions: string;
}

export function useRefineQuote() {
  const queryClient = useQueryClient();

  return useMutation<Quote, ApiError, RefineQuoteVariables>({
    mutationFn: async ({ id, instructions }) => {
      const raw = await api.post<Record<string, unknown>>(`/quotes/${id}/refine`, { instructions });
      return toQuote(raw);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.all });
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(variables.id) });
    },
  });
}

export function useConvertQuoteToInvoice() {
  const queryClient = useQueryClient();

  return useMutation<Invoice, ApiError, string>({
    mutationFn: (id) => api.post(`/quotes/${id}/convert-to-invoice`, {}),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.all });
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: invoiceKeys.all });
    },
  });
}

export function useDeleteQuote() {
  const queryClient = useQueryClient();

  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete(`/quotes/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.all });
    },
  });
}
