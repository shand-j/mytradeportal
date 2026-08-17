import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";
import { config } from "../lib/config";
import { Quote, QuoteStatus } from "../types";

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
  total: string;
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
  lineItems: ApiQuoteLineItem[];
  customer: ApiContact;
};

export async function fetchQuotes(): Promise<ApiQuote[]> {
  return api.get<ApiQuote[]>("/quotes");
}

export async function fetchQuote(id: string): Promise<ApiQuote> {
  return api.get<ApiQuote>(`/quotes/${id}`);
}

/**
 * Generate a draft quote from a lead (quote request) using the real backend AI
 * pipeline (retrieval + LLM + catalogue pricing). Returns the mapped quote.
 * Throws ApiError/NetworkError, which the caller surfaces (e.g. when the LLM is
 * not configured).
 */
export async function generateQuoteFromLead(quoteRequestId: string): Promise<Quote> {
  const q = await api.post<ApiQuote>("/quotes/generate", { quoteRequestId });
  return mapQuote(q);
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
function mapQuote(q: ApiQuote): Quote {
  return {
    id: q.id,
    leadId: "",
    customerName: q.customer?.name ?? "Customer",
    title: q.title,
    postcode: q.customer?.postcode ?? "",
    status: STATUS_MAP[q.status] ?? "sent",
    lineItems: (q.lineItems ?? []).map((li) => ({
      id: li.id,
      kind: "labour" as const,
      description: li.description,
      qty: String(li.quantity),
      unit: "job",
      unitPrice: String(li.unitPrice),
    })),
    assumptions: [],
    sentAt: q.sentAt ?? undefined,
    expiresAt: q.validUntil ?? undefined,
    vatRate: parseFloat(q.vatRate) || 0.2,
  };
}

/**
 * Outstanding-quotes total for the dashboard.
 *
 * In connected mode this comes from the real backend (`GET /quotes`, summing
 * draft + sent). In demo/offline mode the query is disabled and the caller
 * uses its mock figure instead. `isConnected` lets the UI show a "Live" badge.
 */
export function useOutstandingQuotes() {
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: fetchQuotes,
    enabled: config.apiEnabled,
  });

  const total = (query.data ?? [])
    .filter((q) => q.status === "draft" || q.status === "sent")
    .reduce((sum, q) => sum + (parseFloat(q.total) || 0), 0);

  return {
    total,
    count: query.data?.length ?? 0,
    isConnected: config.apiEnabled && query.isSuccess,
    isLoading: query.isLoading,
  };
}

/**
 * Full quotes list for the Quotes screen. Returns backend quotes mapped into
 * the app's `Quote` shape when connected; otherwise an empty list and the
 * caller falls back to mock data. Shares the `["quotes"]` cache with
 * `useOutstandingQuotes`.
 */
export function useQuotesList() {
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: fetchQuotes,
    enabled: config.apiEnabled,
  });

  const isConnected = config.apiEnabled && query.isSuccess;

  return {
    quotes: isConnected ? (query.data ?? []).map(mapQuote) : [],
    isConnected,
    isLoading: config.apiEnabled && query.isLoading,
  };
}

/** A single quote by id (connected mode), mapped to the app `Quote` shape. */
export function useQuote(id: string | undefined) {
  const query = useQuery({
    queryKey: ["quote", id],
    queryFn: () => fetchQuote(id as string),
    enabled: config.apiEnabled && !!id,
  });

  return {
    quote: query.data ? mapQuote(query.data) : undefined,
    isConnected: config.apiEnabled && query.isSuccess,
    isLoading: config.apiEnabled && !!id && query.isLoading,
  };
}
