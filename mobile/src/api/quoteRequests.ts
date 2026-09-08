import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";
import { Lead, LeadStatus, Quote } from "../types";
import { ApiContact, ApiQuote, mapQuote as mapApiQuote } from "./quotes";
import { QuoteFormData, ALL_CATEGORIES } from "../screens/customer/quote-steps/types";

/** Camelized QuoteRequestRead (subset the app uses). */
export type ApiQuoteRequest = {
  id: string;
  source: string;
  rawText: string | null;
  structuredData: Record<string, unknown>;
  aiExtractedSummary: string | null;
  urgency: string;
  status: string;
  safetyReviewRequired: boolean;
  /** True when the AI triage decided a human call-back is needed. */
  requiresCallback?: boolean;
  /** Linked customer (homeowner) account id, when the contact has one. */
  customerId?: string | null;
  createdAt: string;
  customer: ApiContact | null;
  quote: ApiQuote | null;
};

export type PublicQuoteRequestAck = {
  id: string;
  status: string;
  reference: string;
};

function categoryLabel(category: string | undefined): string {
  return ALL_CATEGORIES.find((c) => c.key === category)?.label ?? "New request";
}

/** Category label, or null when the structured data has no known category. */
function knownCategoryLabel(category: string | undefined): string | null {
  if (!category) return null;
  return ALL_CATEGORIES.find((c) => c.key === category)?.label ?? null;
}

/**
 * Best-effort lead title: explicit title, then the known category label, then
 * the AI-extracted job summary, then an excerpt of the customer's raw text.
 * (Seeded/imported requests often carry no structured title/category at all.)
 */
function leadTitle(sd: Record<string, unknown>, qr: ApiQuoteRequest, fallback: string): string {
  const aiExtracted = (sd.aiExtracted ?? {}) as Record<string, unknown>;
  const rawExcerpt = qr.rawText?.trim() ? qr.rawText.trim().slice(0, 80) : null;
  return (
    (sd.title as string | undefined) ||
    knownCategoryLabel(sd.category as string | undefined) ||
    (aiExtracted.job as string | undefined) ||
    qr.aiExtractedSummary ||
    rawExcerpt ||
    fallback
  );
}

function buildRawText(form: QuoteFormData): { title: string; rawText: string | null } {
  if (form.category === "other") {
    const description = (form.questionnaire?.other_description as string) ?? "";
    return {
      title: description.trim() || "Something else",
      rawText: description.trim() || null,
    };
  }
  return {
    title: categoryLabel(form.category),
    rawText: (form.questionnaire?.notes as string) ?? null,
  };
}

/**
 * Submit a homeowner's quote request to a business (no auth required). Maps the
 * captured wizard form into the public payload. Photos staged in the media step
 * are uploaded separately (see api/uploads.ts) once the request exists.
 */
export async function submitPublicQuoteRequest(
  slug: string,
  form: QuoteFormData
): Promise<PublicQuoteRequestAck> {
  const { title, rawText } = buildRawText(form);
  return api.post<PublicQuoteRequestAck>(
    `/businesses/${encodeURIComponent(slug)}/quote-requests`,
    {
      contact: {
        name: form.contact.name,
        email: form.contact.email || null,
        phone: form.contact.mobile || null,
        postcode: form.postcode || null,
      },
      category: form.category,
      title,
      rawText,
      structuredData: {
        property: form.property,
        questionnaire: form.questionnaire,
        budgetContext: form.budgetContext,
        preferredContact: form.contact.preferredContact,
        bestTimeToCall: form.contact.bestTimeToCall,
      },
      urgency: form.urgency || "normal",
      preferredDates: (form.preferredDates ?? []).map((d) => ({ date: d })),
      safetyReviewRequired: form.triage === "emergency" || form.redFlagSymptoms.length > 0,
      marketingConsent: form.consents.marketingOptIn,
    },
    // Attach the customer token when logged in (auth is optional server-side):
    // a present token links the request to the customer's account/history.
    { auth: true }
  );
}

/** Backend quote-request status -> app Lead status. */
const STATUS_MAP: Record<string, LeadStatus> = {
  pending: "new",
  processed: "new",
  draft_quote: "draft",
  converted_to_quote: "converted",
  closed: "dead",
};

/** Map a backend quote request into the trade app's `Lead` shape. */
function mapLead(qr: ApiQuoteRequest): Lead {
  const sd = qr.structuredData ?? {};
  return {
    id: qr.id,
    title: leadTitle(sd, qr, "New request"),
    postcode: qr.customer?.postcode ?? "",
    urgency: qr.urgency,
    // Backend sources are free-form ("qr", "in_app", "web_form", "manual", …);
    // the label helper falls back to the raw value for anything unknown.
    source: (qr.source || "app") as Lead["source"],
    customerName: qr.customer?.name ?? "New customer",
    customerEmail: qr.customer?.email ?? undefined,
    customerPhone: qr.customer?.phone ?? undefined,
    customerId: qr.customerId ?? undefined,
    badge: qr.safetyReviewRequired ? "Flagged" : "New",
    status: STATUS_MAP[qr.status] ?? "new",
    note: qr.rawText ?? undefined,
    createdAt: qr.createdAt,
    structuredData: qr.structuredData,
    requiresCallback: qr.requiresCallback ?? false,
  };
}

export async function fetchLeads(): Promise<ApiQuoteRequest[]> {
  return api.get<ApiQuoteRequest[]>("/quote-requests");
}

export type CreateQuoteRequestInput = {
  contactId?: string;
  source: string;
  rawText?: string | null;
  structuredData?: Record<string, unknown>;
  urgency?: string;
};

/** Create a lead via the staff endpoint (POST /quote-requests). Returns the new id. */
export async function createQuoteRequest(
  input: CreateQuoteRequestInput
): Promise<{ id: string }> {
  return api.post<{ id: string }>("/quote-requests", input);
}

/** The authenticated customer's own quote requests (their history). */
export async function fetchMyRequests(): Promise<ApiQuoteRequest[]> {
  return api.get<ApiQuoteRequest[]>("/customer/quote-requests");
}

/** Customer-facing status derived from a quote request's backend status. */
export type CustomerRequestStatus = "awaiting_review" | "open" | "converted" | "closed";

export type CustomerRequest = {
  id: string;
  title: string;
  postcode: string;
  status: CustomerRequestStatus;
  createdAt: string;
  /** Present when the request has been converted to a quote. */
  quoteId?: string;
  quoteStatus?: "sent" | "approved" | "rejected" | "expired";
  quote?: Quote;
};

const CUSTOMER_STATUS_MAP: Record<string, CustomerRequestStatus> = {
  pending: "awaiting_review",
  processed: "open",
  draft_quote: "open",
  converted_to_quote: "converted",
  closed: "closed",
};

function mapCustomerRequest(qr: ApiQuoteRequest): CustomerRequest {
  const sd = qr.structuredData ?? {};
  const quote = qr.quote;
  return {
    id: qr.id,
    title: leadTitle(sd, qr, "Quote request"),
    postcode: qr.customer?.postcode ?? "",
    status: CUSTOMER_STATUS_MAP[qr.status] ?? "awaiting_review",
    createdAt: qr.createdAt,
    quoteId: quote?.id,
    quoteStatus: (quote?.status as CustomerRequest["quoteStatus"]) ?? undefined,
    quote: quote ? mapApiQuote(quote) : undefined,
  };
}

/** The logged-in customer's quote-request history. Returns mapped requests from the backend. */
export function useMyRequests() {
  const query = useQuery({
    queryKey: ["my-requests"],
    queryFn: fetchMyRequests,
  });

  return {
    requests: (query.data ?? []).map(mapCustomerRequest),
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}

export async function fetchLead(id: string): Promise<Lead> {
  const qr = await api.get<ApiQuoteRequest>(`/quote-requests/${id}`);
  return mapLead(qr);
}

export type LeadUpdateInput = {
  rawText?: string;
  structuredData?: Record<string, unknown>;
  urgency?: string;
  status?: string;
  safetyReviewRequired?: boolean;
};

/** Persist tradesperson edits to a lead (quote request). */
export async function updateLead(id: string, input: LeadUpdateInput): Promise<Lead> {
  const qr = await api.patch<ApiQuoteRequest>(`/quote-requests/${id}`, input);
  return mapLead(qr);
}

/** A single lead (quote request) by id, mapped to the app `Lead` shape. */
export function useLead(id: string | undefined) {
  const query = useQuery({
    queryKey: ["quote-request", id],
    queryFn: () => fetchLead(id as string),
    enabled: !!id,
  });

  return {
    lead: query.data,
    isConnected: query.isSuccess,
    isLoading: !!id && query.isLoading,
  };
}

/** Trade leads list from real quote requests. Returns app `Lead`s from the backend. */
export function useLeadsList() {
  const query = useQuery({
    queryKey: ["quote-requests"],
    queryFn: fetchLeads,
  });

  return {
    // Converted leads are excluded: their quote row represents them in the
    // list, so showing both would duplicate the same work item.
    leads: (query.data ?? []).map(mapLead).filter((lead) => lead.status !== "converted"),
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}
