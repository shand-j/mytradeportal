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
  sentAt?: string;
  expiresAt?: string;
  /** Customer-reconfirmed visit dates captured at acceptance. */
  acceptedDates: string[];
  vatRate: number;
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

export type JobStatus = "confirmed" | "in_progress" | "completed" | "cancelled";

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

export type CircuitTestRow = {
  id: string;
  circuit: string;
  protection: string;
  /** Measured earth-fault loop impedance (Ω). */
  zsMeasured: number;
  /** Max permitted Zs for the protective device (Ω), from BS 7671 tables. */
  zsMax: number;
  /** RCD disconnection time at 5× rated current (ms); ≤40ms passes. */
  rcdTripMs: number;
  /** Insulation resistance (MΩ). */
  ir: number;
};

export type ObservationCode = "C1" | "C2" | "C3" | "FI";

export type CertObservation = {
  id: string;
  code: ObservationCode;
  text: string;
};

export type CertificateType = "EICR" | "EIC" | "MinorWorks";
export type CertificateStatus = "draft" | "issued";

export type Certificate = {
  id: string;
  type: CertificateType;
  customerName: string;
  address: string;
  postcode: string;
  status: CertificateStatus;
  overall: "satisfactory" | "unsatisfactory" | null;
  circuits: CircuitTestRow[];
  observations: CertObservation[];
  createdAt: string;
  signedBy?: string;
  signedAt?: string;
};
