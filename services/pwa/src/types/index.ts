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
};

export type LeadSource = "app" | "qr" | "web" | "whatsapp" | "sms" | "phone" | "manual";

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
  estimate?: string;
  badge: "New" | "Flagged" | "Draft";
  status: LeadStatus;
  note?: string;
  mediaIds?: string[];
  createdAt: string;
  preferredChannel?: "sms" | "whatsapp";
};

export type QuoteStatus = "draft" | "sent" | "accepted" | "rejected" | "expired";

export type QuoteLineItem = {
  id: string;
  kind: "labour" | "materials" | "callout";
  description: string;
  qty: string;
  unit: string;
  unitPrice: string;
};

export type Quote = {
  id: string;
  leadId: string;
  customerName: string;
  title: string;
  postcode: string;
  status: QuoteStatus;
  lineItems: QuoteLineItem[];
  assumptions: string[];
  aiConfidence?: number;
  sentAt?: string;
  expiresAt?: string;
  vatRate: number;
};

export type InvoiceStatus = "draft" | "sent" | "paid" | "overdue";

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
