import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";
import { config } from "../lib/config";
import { Lead, LeadStatus } from "../types";
import { ApiContact } from "./quotes";
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
  createdAt: string;
  customer: ApiContact | null;
};

type PublicQuoteRequestAck = {
  id: string;
  status: string;
  reference: string;
};

function categoryLabel(category: string | undefined): string {
  return ALL_CATEGORIES.find((c) => c.key === category)?.label ?? "New request";
}

/**
 * Submit a homeowner's quote request to a business (no auth). Maps the captured
 * wizard form into the public payload. Media items are local captures in the
 * demo; real uploads are a later slice, so only structured data is sent.
 */
export async function submitPublicQuoteRequest(
  slug: string,
  form: QuoteFormData
): Promise<PublicQuoteRequestAck> {
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
      title: categoryLabel(form.category),
      rawText: form.questionnaire?.notes ?? null,
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
    { auth: false }
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
  const title =
    (sd.title as string | undefined) ||
    categoryLabel(sd.category as string | undefined) ||
    qr.aiExtractedSummary ||
    "New request";
  return {
    id: qr.id,
    title,
    postcode: qr.customer?.postcode ?? "",
    urgency: qr.urgency,
    source: "app",
    customerName: qr.customer?.name ?? "New customer",
    customerEmail: qr.customer?.email ?? undefined,
    customerPhone: qr.customer?.phone ?? undefined,
    badge: qr.safetyReviewRequired ? "Flagged" : "New",
    status: STATUS_MAP[qr.status] ?? "new",
    note: qr.rawText ?? undefined,
    createdAt: qr.createdAt,
  };
}

export async function fetchLeads(): Promise<ApiQuoteRequest[]> {
  return api.get<ApiQuoteRequest[]>("/quote-requests");
}

export async function fetchLead(id: string): Promise<Lead> {
  const qr = await api.get<ApiQuoteRequest>(`/quote-requests/${id}`);
  return mapLead(qr);
}

/** A single lead (quote request) by id, mapped to the app `Lead` shape. */
export function useLead(id: string | undefined) {
  const query = useQuery({
    queryKey: ["quote-request", id],
    queryFn: () => fetchLead(id as string),
    enabled: config.apiEnabled && !!id,
  });

  return {
    lead: query.data,
    isConnected: config.apiEnabled && query.isSuccess,
    isLoading: config.apiEnabled && !!id && query.isLoading,
  };
}

/**
 * Trade leads list from real quote requests. Returns app `Lead`s when connected;
 * otherwise an empty list and the caller falls back to mock leads.
 */
export function useLeadsList() {
  const query = useQuery({
    queryKey: ["quote-requests"],
    queryFn: fetchLeads,
    enabled: config.apiEnabled,
  });

  const isConnected = config.apiEnabled && query.isSuccess;

  return {
    leads: isConnected ? (query.data ?? []).map(mapLead) : [],
    isConnected,
    isLoading: config.apiEnabled && query.isLoading,
  };
}
