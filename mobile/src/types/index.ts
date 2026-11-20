export type AppRole = "trade" | "customer" | "guest";

export type TradeRole = "owner" | "admin" | "office_manager" | "engineer";

export type User = {
  id: string;
  email: string;
  fullName: string;
  role: TradeRole;
};

export type BusinessConfig = {
  slug: string;
  code: string;
  name: string;
  primaryColor: string;
  secondaryColor: string;
  logoUrl?: string;
  businessServices?: string[];
  contactPhone?: string;
  address?: string;
  /** Public review link (Google/Checkatrade/Trustpilot) shown after payment. */
  reviewUrl?: string;
  /** Onboarding metrics: typical quoting volume (used for the time-saved card). */
  quotesPerWeek?: number;
  avgMinutesPerQuote?: number;
};

export type LeadSource =
  | "app"
  | "in_app"
  | "qr"
  | "web"
  | "web_form"
  | "whatsapp"
  | "sms"
  | "phone"
  | "manual";

export type LeadStatus = "new" | "draft" | "site_visit" | "dead" | "converted";

export type Lead = {
  id: string;
  title: string;
  postcode: string;
  urgency: string;
  source: LeadSource;
  customerName: string;
  customerPhone?: string;
  customerEmail?: string;
  /** Linked customer (homeowner) account id, when the lead's contact has one. */
  customerId?: string;
  estimate?: string;
  badge: "New" | "Flagged" | "Draft";
  status: LeadStatus;
  note?: string;
  mediaIds?: string[];
  createdAt: string;
  preferredChannel?: "sms" | "whatsapp";
  /** Captured customer quote-request data (property, questionnaire, budget, etc.). */
  structuredData?: Record<string, unknown>;
  /** True when the AI triage flagged this lead as needing a human call back. */
  requiresCallback?: boolean;
  /**
   * True only when the customer can receive in-app chat (claimed password or
   * push token registered). Auto-provisioned web-form customers are false —
   * chat must not be offered; follow up by phone/email. Undefined when the
   * backend does not report reachability (treat as reachable).
   */
  customerReachable?: boolean;
  /** The customer's preferred follow-up channel, when captured. */
  contactPreferredMethod?: "email" | "phone" | null;
  /** Linked quote id when the lead has been (auto-)converted to a quote. */
  quoteId?: string;
  /** Backend status of the linked quote ("draft" while awaiting tradesperson review). */
  quoteStatus?: string;
  /** Total (£) of the linked quote, when one exists. */
  quoteTotal?: number;
};

export type QuoteStatus =
  | "draft"
  | "sent"
  | "accepted"
  | "rejected"
  | "expired"
  | "invoiced"
  | "cancelled";

export type QuoteLineItem = {
  id: string;
  kind: "labour" | "materials" | "callout";
  description: string;
  qty: string;
  unit: string;
  unitPrice: string;
  /** True when the line was drafted by the AI pipeline (manual lines are false). */
  aiGenerated: boolean;
};

export type Quote = {
  id: string;
  leadId: string;
  /** Backend quote_request_id; used to open the linked chat thread. */
  quoteRequestId?: string;
  /** CRM contact id; lets the chat button find-or-create a thread (C7). */
  customerId?: string;
  customerName: string;
  title: string;
  postcode: string;
  status: QuoteStatus;
  lineItems: QuoteLineItem[];
  assumptions: string[];
  /** True when the quote was drafted by the AI pipeline. */
  aiGenerated: boolean;
  /** AI confidence 0–1, or null when not applicable. */
  aiConfidence: number | null;
  aiWarnings: string[];
  aiAssumptions: string[];
  aiNotes: string | null;
  /** "grounded" | "no_index" | "skipped_no_key" | null — catalogue retrieval status. */
  retrievalStatus: string | null;
  /** One-sentence summary of what the last AI refine changed (null before any refine). */
  aiRefineSummary?: string | null;
  /** The electrician's thumbs up/down on the last refine, when rated. */
  aiRefineRating?: "up" | "down" | null;
  sentAt?: string;
  expiresAt?: string;
  /** Customer-reconfirmed visit dates captured at acceptance. */
  acceptedDates: string[];
  vatRate: number;
  /** Server totals (ex VAT, VAT amount, VAT-inclusive total). `total` already
   * includes any tenant quote-rounding uplift; display these instead of
   * recomputing from line items so every surface shows the same value. */
  subtotal?: number;
  vatAmount?: number;
  total?: number;
  roundingAdjustment?: number;
};

export type CircuitTestRow = {
  id: string;
  circuit: string;
  protection: string;
  zsMeasured: number;
  zsMax: number;
  rcdTripMs: number;
  ir: number;
};

export type CertObservation = {
  id: string;
  code: "C1" | "C2" | "C3" | "FI";
  text: string;
};

export type Certificate = {
  id: string;
  customerName: string;
  address: string;
  postcode: string;
  status: "draft" | "issued";
  circuits: CircuitTestRow[];
  observations: CertObservation[];
  issuedAt?: string;
};

export type InvoiceStatus = "draft" | "sent" | "paid" | "overdue" | "refunded";

export type Invoice = {
  id: string;
  quoteId: string;
  customerName: string;
  title: string;
  amount: number;
  status: InvoiceStatus;
  dueDate: string;
  sentAt?: string;
  paidAt?: string;
};

export type JobStatus = "draft" | "confirmed" | "in_progress" | "completed" | "cancelled";

export type Job = {
  id: string;
  quoteId: string;
  title: string;
  customerName: string;
  postcode: string;
  address: string;
  status: JobStatus;
  assignedTo: string;
  date: string;
  time: string;
  /** "HH:MM" end time, when the backend scheduled an end. */
  endTime?: string;
  phone: string;
  materialCost?: number;
  labourCost?: number;
};

export type Customer = {
  id: string;
  name: string;
  email: string;
  phone: string;
  postcode: string;
  address?: string;
  lifetimeValue: number;
  quoteCount: number;
  jobCount: number;
  lastContact: string;
  notes?: string;
};

export type MediaAsset = {
  id: string;
  uri: string;
  type: "image" | "video";
  caption?: string;
  createdAt: string;
};

export type FollowUpChannel = "sms" | "email";

export type FollowUpSettings = {
  quoteReminderEnabled: boolean;
  invoiceReminderEnabled: boolean;
  quoteReminderDelayDays: number;
  invoiceReminderDelayDays: number;
  channel: FollowUpChannel;
};
