import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AI_TIMEOUT_MS, api } from "../lib/apiClient";
import { Quote, QuoteLineItem, QuoteStatus } from "../types";

/** Contact as returned nested on quotes/jobs (camelized ContactRead). */
export type ApiContact = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  postcode: string | null;
};

type ApiQuoteLineItem = {
  id: string;
  description: string;
  quantity: string;
  unitPrice: string;
  unit?: string;
  total: string;
  aiGenerated?: boolean;
};

/** Full backend quote shape (camelized QuoteRead). */
export type ApiQuote = {
  id: string;
  title: string;
  status: string;
  subtotal: string;
  vatRate: string;
  vatAmount: string;
  total: string;
  validUntil: string | null;
  sentAt: string | null;
  /** Customer-reconfirmed visit dates captured at acceptance (free-text strings). */
  acceptedDates?: string[];
  lineItems: ApiQuoteLineItem[];
  quoteRequestId: string | null;
  customer: ApiContact;
  aiGenerated?: boolean;
  aiConfidence?: number | null;
  aiWarnings?: string[];
  aiAssumptions?: string[];
  aiNotes?: string | null;
  retrievalStatus?: string | null;
};

export async function fetchQuotes(): Promise<ApiQuote[]> {
  return api.get<ApiQuote[]>("/quotes");
}

export async function fetchQuote(id: string): Promise<ApiQuote> {
  return api.get<ApiQuote>(`/quotes/${id}`);
}

export type GenerateQuoteInput = {
  quoteRequestId: string;
  /** Free-text notes / extra description to feed the Kimi API. */
  description?: string;
  /** Property type, e.g. "House", "Flat". */
  propertyType?: string;
  /** Additional structured intake answers (parking, access, bedrooms, etc.). */
  siteSurvey?: Record<string, unknown>;
};

export type GenerateStandaloneQuoteInput = {
  /** Plain-English job description (backend requires >= 5 chars). */
  description: string;
  /** Optional customer name; the backend creates a "Generated lead" contact. */
  customerName?: string;
  propertyType?: string;
  siteSurvey?: Record<string, unknown>;
};

/**
 * Generate a draft quote without a lead (quote request): the electrician types
 * a plain-English job description and the backend creates a placeholder
 * contact ("Generated lead" when no name is given).
 */
export async function generateQuoteStandalone(
  input: GenerateStandaloneQuoteInput
): Promise<Quote> {
  const q = await api.post<ApiQuote>(
    "/quotes/generate",
    {
      description: input.description,
      customerName: input.customerName,
      propertyType: input.propertyType,
      siteSurvey: input.siteSurvey,
    },
    { timeoutMs: AI_TIMEOUT_MS }
  );
  return mapQuote(q);
}

/**
 * Generate a draft quote from a lead (quote request) using the backend AI
 * pipeline routed through the Kimi API. Returns the mapped quote.
 */
export async function generateQuoteFromLead(input: GenerateQuoteInput): Promise<Quote> {
  const q = await api.post<ApiQuote>(
    "/quotes/generate",
    {
      quoteRequestId: input.quoteRequestId,
      description: input.description ?? "",
      propertyType: input.propertyType,
      siteSurvey: input.siteSurvey,
    },
    { timeoutMs: AI_TIMEOUT_MS }
  );
  return mapQuote(q);
}

export type GenerateQuoteAsyncInput = {
  /** Lead to generate from; omit for lead-less generation. */
  quoteRequestId?: string;
  /** Plain-English job description / notes. */
  description?: string;
  /** Lead-less mode: customer name for the generated contact. */
  customerName?: string;
  /** Lead-less mode: existing CRM contact to attach the quote to. */
  contactId?: string;
  propertyType?: string;
  siteSurvey?: Record<string, unknown>;
};

export type GenerateQuoteAsyncAck = {
  status: string;
  quoteRequestId: string | null;
};

/**
 * Kick off AI quote generation in the background (POST /quotes/generate-async,
 * 202 Accepted). The backend emits a quote_ready/quote_failed notification
 * when the job finishes — the app polls notifications instead of blocking.
 */
export async function generateQuoteAsync(
  input: GenerateQuoteAsyncInput
): Promise<GenerateQuoteAsyncAck> {
  return api.post<GenerateQuoteAsyncAck>("/quotes/generate-async", {
    quoteRequestId: input.quoteRequestId,
    description: input.description ?? "",
    customerName: input.customerName,
    contactId: input.contactId,
    propertyType: input.propertyType,
    siteSurvey: input.siteSurvey,
  });
}

/**
 * Generate an AI draft quote for an existing CRM contact (POST /quotes/generate
 * with contact_id). Used by the quote-less job → AI invoice flow, where the
 * generated lines become the invoice's line items.
 */
export async function generateQuoteForContact(input: {
  contactId: string;
  description: string;
}): Promise<ApiQuote> {
  return api.post<ApiQuote>(
    "/quotes/generate",
    { contactId: input.contactId, description: input.description },
    { timeoutMs: AI_TIMEOUT_MS }
  );
}

/** Mark a quote as sent to the customer (POST /quotes/{id}/send). */
export async function sendQuote(id: string): Promise<void> {
  await api.post(`/quotes/${id}/send`);
}

/**
 * Refine an AI-generated quote with free-text instructions
 * (POST /quotes/{id}/refine). Returns the mapped updated quote.
 */
export async function refineQuote(id: string, instructions: string): Promise<Quote> {
  const q = await api.post<ApiQuote>(
    `/quotes/${id}/refine`,
    { instructions },
    { timeoutMs: AI_TIMEOUT_MS }
  );
  return mapQuote(q);
}

/** Update a quote's editable line items (PATCH /quotes/{id}). */
export async function updateQuote(
  id: string,
  lineItems: QuoteLineItem[],
  vatRate: number
): Promise<ApiQuote> {
  return api.patch<ApiQuote>(`/quotes/${id}`, {
    lineItems: lineItems.map((li) => ({
      description: li.description,
      quantity: parseFloat(li.qty) || 0,
      unitPrice: parseFloat(li.unitPrice) || 0,
      // Round-trip the AI lineage flag: dropping it breaks refine/analytics.
      aiGenerated: li.aiGenerated,
    })),
    vatRate,
  });
}

/** Approve or reject a quote (POST /quotes/{id}/approve). */
export async function setQuoteApproval(id: string, approved: boolean): Promise<ApiQuote> {
  return api.post<ApiQuote>(`/quotes/${id}/approve`, { approved });
}

/**
 * Customer accepts a sent quote (POST /customer/quotes/{id}/accept).
 * When `preferredDates` is provided it is sent as the JSON body so the backend
 * persists the customer's reconfirmed visit dates on the quote; otherwise the
 * request keeps its legacy body-less form.
 */
export async function acceptCustomerQuote(
  id: string,
  preferredDates?: string[]
): Promise<ApiQuote> {
  return api.post<ApiQuote>(
    `/customer/quotes/${id}/accept`,
    preferredDates !== undefined ? { preferredDates } : undefined
  );
}

/** Customer rejects a sent quote (POST /customer/quotes/{id}/reject). */
export async function rejectCustomerQuote(id: string): Promise<ApiQuote> {
  return api.post<ApiQuote>(`/customer/quotes/${id}/reject`);
}

/** Mutation: update a quote's line items and refresh the quotes caches. */
export function useUpdateQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, lineItems, vatRate }: { id: string; lineItems: QuoteLineItem[]; vatRate: number }) =>
      updateQuote(id, lineItems, vatRate),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["quotes"] });
      qc.invalidateQueries({ queryKey: ["quote", id] });
      qc.invalidateQueries({ queryKey: ["my-quotes"] });
    },
  });
}

/** Mutation: refine an AI quote with instructions and refresh the quote caches. */
export function useRefineQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, instructions }: { id: string; instructions: string }) =>
      refineQuote(id, instructions),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["quotes"] });
      qc.invalidateQueries({ queryKey: ["quote", id] });
      qc.invalidateQueries({ queryKey: ["my-quotes"] });
    },
  });
}

/** Convert an approved/sent quote into a draft invoice. */
export async function convertQuoteToInvoice(id: string): Promise<{ id: string }> {
  return api.post<{ id: string }>(`/quotes/${id}/convert-to-invoice`, {});
}

/** Mutation: convert a quote to an invoice and navigate the caches to the new invoice. */
export function useConvertQuoteToInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => convertQuoteToInvoice(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quotes"] });
      qc.invalidateQueries({ queryKey: ["invoices"] });
    },
  });
}

/** Mutation: send a quote and refresh the quotes caches. */
export function useSendQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => sendQuote(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["quotes"] });
      qc.invalidateQueries({ queryKey: ["quote", id] });
      qc.invalidateQueries({ queryKey: ["my-quotes"] });
      qc.invalidateQueries({ queryKey: ["my-requests"] });
    },
  });
}

/** Backend uses "approved"; the app's UI vocabulary uses "accepted". */
const STATUS_MAP: Record<string, QuoteStatus> = {
  draft: "draft",
  sent: "sent",
  approved: "accepted",
  accepted: "accepted",
  rejected: "rejected",
  expired: "expired",
};

/** Map a backend quote into the app's display `Quote` shape. */
export function mapQuote(q: ApiQuote): Quote {
  return {
    id: q.id,
    leadId: "",
    quoteRequestId: q.quoteRequestId ?? undefined,
    customerName: q.customer?.name ?? "Customer",
    title: q.title,
    postcode: q.customer?.postcode ?? "",
    status: STATUS_MAP[q.status] ?? "sent",
    lineItems: (q.lineItems ?? []).map((li) => ({
      id: li.id,
      kind: "labour" as const,
      description: li.description,
      qty: String(li.quantity),
      unit: li.unit ?? "ea",
      unitPrice: String(li.unitPrice),
      aiGenerated: li.aiGenerated ?? false,
    })),
    assumptions: [],
    aiGenerated: q.aiGenerated ?? false,
    aiConfidence: q.aiConfidence ?? null,
    aiWarnings: q.aiWarnings ?? [],
    aiAssumptions: q.aiAssumptions ?? [],
    aiNotes: q.aiNotes ?? null,
    retrievalStatus: q.retrievalStatus ?? null,
    sentAt: q.sentAt ?? undefined,
    expiresAt: q.validUntil ?? undefined,
    acceptedDates: q.acceptedDates ?? [],
    vatRate: Number.isFinite(parseFloat(q.vatRate)) ? parseFloat(q.vatRate) : 0.2,
  };
}

/**
 * Outstanding-quotes total for the dashboard.
 *
 * Sums draft + sent quotes from `GET /quotes`. `isConnected` lets the UI show a "Live" badge.
 */
export function useOutstandingQuotes() {
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: fetchQuotes,
  });

  const total = (query.data ?? [])
    .filter((q) => q.status === "draft" || q.status === "sent")
    .reduce((sum, q) => sum + (parseFloat(q.total) || 0), 0);

  return {
    total,
    count: query.data?.length ?? 0,
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}

/**
 * Full quotes list for the Quotes screen. Returns backend quotes mapped into
 * the app's `Quote` shape. Shares the `["quotes"]` cache with
 * `useOutstandingQuotes`.
 */
export function useQuotesList() {
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: fetchQuotes,
  });

  return {
    quotes: (query.data ?? []).map(mapQuote),
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}

/** A single quote by id, mapped to the app `Quote` shape. */
export function useQuote(id: string | undefined) {
  const query = useQuery({
    queryKey: ["quote", id],
    queryFn: () => fetchQuote(id as string),
    enabled: !!id,
  });

  return {
    quote: query.data ? mapQuote(query.data) : undefined,
    isConnected: query.isSuccess,
    isLoading: !!id && query.isLoading,
  };
}

/** Quotes sent to the authenticated customer. */
export async function fetchMyQuotes(): Promise<ApiQuote[]> {
  return api.get<ApiQuote[]>("/customer/quotes");
}

/** The logged-in customer's quote history. Returns backend quotes mapped into the app's `Quote` shape. */
export function useMyQuotes() {
  const query = useQuery({
    queryKey: ["my-quotes"],
    queryFn: fetchMyQuotes,
  });

  return {
    quotes: (query.data ?? []).map(mapQuote),
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}

/** Mutation: customer accepts a quote and refreshes the relevant caches. */
export function useAcceptCustomerQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, preferredDates }: { id: string; preferredDates?: string[] }) =>
      acceptCustomerQuote(id, preferredDates),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["my-quotes"] });
      qc.invalidateQueries({ queryKey: ["quote", id] });
      qc.invalidateQueries({ queryKey: ["my-requests"] });
    },
  });
}

/** Mutation: customer rejects a quote and refreshes the relevant caches. */
export function useRejectCustomerQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => rejectCustomerQuote(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["my-quotes"] });
      qc.invalidateQueries({ queryKey: ["quote", id] });
      qc.invalidateQueries({ queryKey: ["my-requests"] });
    },
  });
}
