export type QuoteStatus = 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired';
export type JobStatus = 'scheduled' | 'in_progress' | 'completed' | 'cancelled';
export type InvoiceStatus = 'draft' | 'sent' | 'viewed' | 'paid' | 'overdue' | 'cancelled';
export type AppointmentStatus = 'scheduled' | 'confirmed' | 'in_progress' | 'completed' | 'cancelled' | 'no_show';
export type UserRole = 'admin' | 'manager' | 'technician';
export type SourceChannel = 'pwa' | 'chatbot' | 'voice' | 'whatsapp' | 'referral' | 'manual';
export type PaymentMethod = 'card' | 'bank_transfer' | 'cash' | 'check';

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  logoUrl: string | null;
  primaryColor: string;
  secondaryColor: string;
  hourlyLaborRate: number;
  dailyLaborRate?: number;
  mateDailyRate?: number;
  matePercent?: number;
  markupPercentage: number;
  minMarginPercent?: number;
  priceTolerancePercent?: number;
  minimumCharge: number;
  vatRate: number;
  email: string;
  phone: string;
  website: string | null;
  address: string;
  planTier: 'starter' | 'professional' | 'complete';
  googlePlaceId: string | null;
  createdAt: string;
}

export interface User {
  id: string;
  tenantId: string;
  fullName: string;
  email: string;
  phone: string | null;
  role: UserRole;
  avatarUrl: string | null;
  isActive: boolean;
}

export interface Customer {
  id: string;
  firstName: string;
  lastName: string;
  email: string | null;
  phone: string;
  address: string | null;
  postcode: string | null;
  propertyType: 'house' | 'apartment' | 'commercial' | null;
  sourceChannel: SourceChannel;
  lifetimeValue: number;
  reviewCount: number;
  averageRating: number | null;
  notes: string | null;
  avatarUrl: string | null;
  createdAt: string;
}

export interface QuoteLineItem {
  id: string;
  description: string;
  quantity: number;
  unit: string;
  unitPrice: number;
  total: number;
  isAiSuggested: boolean;
}

export interface BoQLineItem {
  id: string;
  code: string;
  description: string;
  category: string | null;
  unit: string;
  quantity: number;
  labourHours: number;
  labourRate: number;
  labourTotal: number;
  materialCost: number;
  materialTotal: number;
  plantCost: number;
  plantTotal: number;
  unitPrice: number;
  total: number;
  supplier: string | null;
  brand: string | null;
  sku: string | null;
  productUrl: string | null;
  retailPriceInclVat: number | null;
  notes: string | null;
}

export interface CustomerSummaryLine {
  description: string;
  total: number;
}

export interface MarginIndicator {
  materialSubtotal: number;
  labourSubtotal: number;
  subtotal: number;
  targetMarkupPercent: number;
  estimatedMarginPercent: number;
  estimatedMarginAmount: number;
}

export interface BillOfQuantities {
  id: string;
  quoteId: string;
  status: string;
  notes: string | null;
  subtotal: number;
  vatRate: number;
  vatAmount: number;
  total: number;
  confidence: number;
  warnings: string[];
  regulatoryCitations: Array<Record<string, unknown>>;
  complianceWarnings: string[];
  customerSummaryLines: CustomerSummaryLine[];
  marginIndicator: MarginIndicator | null;
  standard: string | null;
  lineItems: BoQLineItem[];
  suppliers: string[];
  createdAt: string;
  updatedAt: string;
}

export interface Quote {
  id: string;
  reference: string;
  customerId: string;
  customer: Customer;
  status: QuoteStatus;
  lineItems: QuoteLineItem[];
  billOfQuantities: BillOfQuantities | null;
  subtotal: number;
  vatAmount: number;
  vatRate: number;
  total: number;
  aiGenerated: boolean;
  aiConfidenceScore: number | null;
  serviceType: string;
  propertyAddress: string;
  customerMessage: string | null;
  internalNotes: string | null;
  expiresAt: string | null;
  acceptedAt: string | null;
  sentAt: string | null;
  createdAt: string;
}

export interface Job {
  id: string;
  reference: string;
  customerId: string;
  customer: Customer;
  quoteId: string | null;
  status: JobStatus;
  serviceType: string;
  description: string | null;
  scheduledDate: string;
  scheduledTimeStart: string | null;
  scheduledTimeEnd: string | null;
  technicianId: string | null;
  technicianName: string | null;
  propertyAddress: string;
  value: number;
  completionNotes: string | null;
  photos: string[];
  createdAt: string;
}

export interface Appointment {
  id: string;
  customerId: string;
  customer: Customer;
  jobId: string | null;
  title: string;
  startTime: string;
  endTime: string;
  serviceType: string;
  propertyAddress: string;
  status: AppointmentStatus;
  technicianName: string | null;
}

export interface InvoiceLineItem {
  id: string;
  description: string;
  quantity: number;
  unit: string;
  unitPrice: number;
  total: number;
}

export interface Invoice {
  id: string;
  reference: string;
  customerId: string;
  customer: Customer;
  jobId: string | null;
  quoteId: string | null;
  status: InvoiceStatus;
  lineItems: InvoiceLineItem[];
  subtotal: number;
  vatAmount: number;
  vatRate: number;
  total: number;
  amountPaid: number;
  amountDue: number;
  issueDate: string;
  dueDate: string;
  paidAt: string | null;
  paymentMethod: PaymentMethod | null;
  createdAt: string;
}

export type ReviewPlatform = 'google' | 'trustpilot' | 'yell' | 'facebook';

export interface Review {
  id: string;
  customerId: string;
  customer: Customer;
  platform: ReviewPlatform;
  rating: number;
  reviewText: string;
  reviewerName: string;
  responded: boolean;
  responseText: string | null;
  respondedAt: string | null;
  reviewDate: string;
}

export interface Activity {
  id: string;
  type: 'quote_created' | 'quote_sent' | 'quote_accepted' | 'quote_rejected' |
        'job_scheduled' | 'job_started' | 'job_completed' | 'job_cancelled' |
        'invoice_created' | 'invoice_sent' | 'invoice_paid' | 'invoice_overdue' |
        'customer_registered' | 'review_received' | 'ai_quote_generated' | 'payment_received' | 'voice_call_handled';
  title: string;
  description: string | null;
  entityType: string;
  entityId: string;
  createdAt: string;
}

export interface Notification {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message: string;
  entityType: string | null;
  entityId: string | null;
  read: boolean;
  createdAt: string;
}

export interface ServiceOffering {
  id: string;
  name: string;
  description: string | null;
  basePrice: number | null;
  estimatedDuration: number | null;
  category: string;
  isActive: boolean;
}

export interface IntegrationStatus {
  provider: 'quickbooks' | 'xero' | 'stripe' | 'twilio' | 'whatsapp' | 'google_reviews';
  connected: boolean;
  accountName: string | null;
  accountIdentifier: string | null;
  lastSyncAt: string | null;
}

export interface KpiData {
  revenueThisMonth: number;
  revenueChange: number;
  activeJobs: number;
  jobsCapacity: number;
  pendingQuotes: number;
  pendingQuotesValue: number;
  quotesExpiringSoon: number;
  averageRating: number;
  reviewCount: number;
}

export interface DemandForecast {
  predictions: { week: string; predictedJobs: number; confidence: number }[];
  insight: string;
}

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
}

export interface Contact {
  id: string;
  tenantId: string;
  firstName: string;
  lastName: string;
  email: string | null;
  phone: string;
  address: string | null;
  postcode: string | null;
  propertyType: 'house' | 'apartment' | 'commercial' | null;
  sourceChannel: SourceChannel;
  lifetimeValue: number;
  reviewCount: number;
  averageRating: number | null;
  notes: string | null;
  avatarUrl: string | null;
  createdAt: string;
  updatedAt?: string;
}

export interface RevenueChartData {
  labels: string[];
  revenue: number[];
  target: number[];
}

export interface ServiceBreakdownItem {
  service: string;
  percentage: number;
  revenue: number;
  color: string;
}

export interface VoiceStats {
  callsToday: number;
  resolutionRate: number;
  quotesFromVoice: number;
  avgCallDuration: string;
}

export interface DashboardData {
  kpi: KpiData;
  revenueChart: RevenueChartData;
  serviceBreakdown: ServiceBreakdownItem[];
  recentActivity: Activity[];
  voiceStats?: VoiceStats;
}

export interface AiQuotePerformance {
  totalGenerated: number;
  acceptanceRate: number;
  averageValue: number;
  averageGenerationTime: number;
  monthlyData: {
    month: string;
    aiQuotes: number;
    manualQuotes: number;
    aiAcceptance: number;
    manualAcceptance: number;
  }[];
}

export interface VoiceCall {
  caller: string;
  duration: string;
  outcome: string;
  quoteAdjusted: boolean;
  date: string;
}

export interface VoiceAnalytics {
  totalCalls: number;
  averageDuration: string;
  resolutionRate: number;
  totalRevenue: number;
  recentCalls: VoiceCall[];
}

export interface AiInsightsData {
  aiQuotePerformance: AiQuotePerformance;
  voiceAnalytics?: VoiceAnalytics;
  demandForecast?: DemandForecast;
}

export interface ReviewPlatformBreakdown {
  platform: string;
  count: number;
  average: number;
}

export interface ReviewStats {
  averageRating: number;
  totalReviews: number;
  thisMonthCount: number;
  thisMonthChange: number;
  responseRate: number;
  platformBreakdown: ReviewPlatformBreakdown[];
}

export interface AvailabilitySlot {
  startTime: string;
  endTime: string;
}

export type CommunicationChannel = 'voice' | 'chat' | 'sms' | 'whatsapp' | 'email';
export type CommunicationDirection = 'inbound' | 'outbound';

export interface CommunicationMetadata {
  duration?: string | number;
  transcriptUrl?: string;
  aiHandled?: boolean;
  sentiment?: string;
  [key: string]: unknown;
}

export interface Communication {
  id: string;
  tenantId: string;
  contactId: string;
  contact?: Contact;
  channel: CommunicationChannel;
  direction: CommunicationDirection;
  content: string;
  metadata?: CommunicationMetadata;
  createdAt: string;
}

export interface PresignedUpload {
  uploadUrl: string;
  key: string;
  fields?: Record<string, string>;
  publicUrl?: string;
}
