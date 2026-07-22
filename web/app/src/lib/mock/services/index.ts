import type { KpiData, Quote, Job, Customer, Invoice, DemandForecast } from '@/types';
import { mockTenant, mockUsers } from '../data/tenant';
import { mockCustomers } from '../data/customers';
import { mockQuotes } from '../data/quotes';
import { mockJobs } from '../data/jobs';
import { mockInvoices } from '../data/invoices';
import { mockReviews } from '../data/reviews';
import { mockAppointments } from '../data/appointments';
import { mockActivities } from '../data/activities';
import { mockServices } from '../data/services';
import { mockNotifications } from '../data/notifications';

const delay = (ms = 300) => new Promise(r => setTimeout(r, ms + Math.random() * 200));

export const mockDashboardService = {
  async getKpiData(): Promise<KpiData> {
    await delay();
    return {
      revenueThisMonth: 12450,
      revenueChange: 23,
      activeJobs: 8,
      jobsCapacity: 12,
      pendingQuotes: 5,
      pendingQuotesValue: 18200,
      quotesExpiringSoon: 2,
      averageRating: 4.8,
      reviewCount: 47,
    };
  },
  async getRevenueChart(period: string) {
    await delay();
    const data: Record<string, { labels: string[]; revenue: number[]; target: number[] }> = {
      week: { labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], revenue: [450, 680, 320, 890, 1200, 560, 0], target: [500, 500, 500, 500, 500, 500, 0] },
      month: { labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'], revenue: [8200, 9100, 7800, 10200, 9500, 12450], target: [8000, 8000, 8000, 8000, 8000, 8000] },
      year: { labels: ['2023 H2', '2024 H1', '2024 H2', '2025 H1'], revenue: [42000, 58000, 72000, 85000], target: [40000, 50000, 60000, 70000] },
    };
    return data[period] || data.month;
  },
  async getServiceBreakdown() {
    await delay();
    return [
      { service: 'Installation', percentage: 40, revenue: 4980, color: '#2563EB' },
      { service: 'Testing & Certs', percentage: 25, revenue: 3112, color: '#D4650A' },
      { service: 'Emergency', percentage: 20, revenue: 2490, color: '#16A34A' },
      { service: 'Renewable', percentage: 15, revenue: 1867, color: '#A8A29E' },
    ];
  },
  async getRecentActivity(limit = 5) {
    await delay();
    return mockActivities.slice(0, limit);
  },
};

export const mockQuoteService = {
  async listQuotes() {
    await delay();
    return { quotes: mockQuotes, total: mockQuotes.length };
  },
  async getQuote(id: string): Promise<Quote> {
    await delay();
    const quote = mockQuotes.find(q => q.id === id);
    if (!quote) throw new Error('Quote not found');
    return quote;
  },
};

export const mockJobService = {
  async listJobs() {
    await delay();
    return { jobs: mockJobs, total: mockJobs.length };
  },
  async getJob(id: string): Promise<Job> {
    await delay();
    const job = mockJobs.find(j => j.id === id);
    if (!job) throw new Error('Job not found');
    return job;
  },
};

export const mockCustomerService = {
  async listCustomers() {
    await delay();
    return { customers: mockCustomers, total: mockCustomers.length };
  },
  async getCustomer(id: string): Promise<Customer> {
    await delay();
    const customer = mockCustomers.find(c => c.id === id);
    if (!customer) throw new Error('Customer not found');
    return customer;
  },
};

export const mockInvoiceService = {
  async listInvoices() {
    await delay();
    return { invoices: mockInvoices, total: mockInvoices.length };
  },
  async getInvoice(id: string): Promise<Invoice> {
    await delay();
    const invoice = mockInvoices.find(i => i.id === id);
    if (!invoice) throw new Error('Invoice not found');
    return invoice;
  },
};

export const mockCalendarService = {
  async getAppointments() {
    await delay();
    return mockAppointments;
  },
};

export const mockReviewService = {
  async listReviews() {
    await delay();
    return { reviews: mockReviews, total: mockReviews.length };
  },
  async getReviewStats() {
    await delay();
    return {
      averageRating: 4.8,
      totalReviews: 47,
      thisMonthCount: 12,
      thisMonthChange: 5,
      responseRate: 85,
      platformBreakdown: [
        { platform: 'google', count: 42, average: 4.8 },
        { platform: 'trustpilot', count: 3, average: 4.3 },
        { platform: 'yell', count: 2, average: 4.0 },
      ],
    };
  },
};

export const mockAiService = {
  async getQuotePerformance() {
    await delay();
    return {
      totalGenerated: 156,
      acceptanceRate: 87,
      averageValue: 245,
      averageGenerationTime: 4.2,
      monthlyData: [
        { month: 'Jan', aiQuotes: 18, manualQuotes: 8, aiAcceptance: 82, manualAcceptance: 65 },
        { month: 'Feb', aiQuotes: 22, manualQuotes: 6, aiAcceptance: 85, manualAcceptance: 70 },
        { month: 'Mar', aiQuotes: 20, manualQuotes: 10, aiAcceptance: 80, manualAcceptance: 60 },
        { month: 'Apr', aiQuotes: 28, manualQuotes: 5, aiAcceptance: 90, manualAcceptance: 72 },
        { month: 'May', aiQuotes: 32, manualQuotes: 7, aiAcceptance: 88, manualAcceptance: 68 },
        { month: 'Jun', aiQuotes: 36, manualQuotes: 4, aiAcceptance: 92, manualAcceptance: 75 },
      ],
    };
  },
  async getVoiceAnalytics() {
    await delay();
    return {
      totalCalls: 48,
      averageDuration: '3m 24s',
      resolutionRate: 92,
      totalRevenue: 1840,
      recentCalls: [
        { caller: 'Emma Wilson', duration: '4m 12s', outcome: 'Quote booked', quoteAdjusted: true, date: '2025-06-19' },
        { caller: 'Unknown', duration: '2m 08s', outcome: 'General enquiry', quoteAdjusted: false, date: '2025-06-18' },
        { caller: 'David Smith', duration: '5m 45s', outcome: 'Emergency booked', quoteAdjusted: false, date: '2025-06-18' },
        { caller: 'Sarah Johnson', duration: '3m 30s', outcome: 'Quote refinement', quoteAdjusted: true, date: '2025-06-15' },
      ],
    };
  },
  async getDemandForecast(): Promise<DemandForecast> {
    await delay();
    return {
      predictions: [
        { week: 'Jun 23', predictedJobs: 8, confidence: 85 },
        { week: 'Jun 30', predictedJobs: 9, confidence: 82 },
        { week: 'Jul 7', predictedJobs: 7, confidence: 78 },
        { week: 'Jul 14', predictedJobs: 6, confidence: 75 },
        { week: 'Jul 21', predictedJobs: 10, confidence: 80 },
        { week: 'Jul 28', predictedJobs: 11, confidence: 83 },
        { week: 'Aug 4', predictedJobs: 9, confidence: 79 },
        { week: 'Aug 11', predictedJobs: 8, confidence: 76 },
      ],
      insight: 'Forecast: 35% increase in boiler service requests expected in October. Consider scheduling maintenance reminder campaign.',
    };
  },
};

export const mockNotificationService = {
  async listNotifications() {
    await delay();
    return mockNotifications;
  },
  async getUnreadCount() {
    await delay(100);
    return mockNotifications.filter(n => !n.read).length;
  },
};

export const mockSettingsService = {
  async getBusinessSettings() {
    await delay();
    return {
      name: mockTenant.name,
      email: mockTenant.email,
      phone: mockTenant.phone,
      website: mockTenant.website || '',
      address: mockTenant.address,
      hourlyRate: mockTenant.hourlyLaborRate,
      markup: mockTenant.markupPercentage,
      minimumCharge: mockTenant.minimumCharge,
      vatRate: mockTenant.vatRate,
    };
  },
  async listServices() {
    await delay();
    return mockServices;
  },
  async getIntegrations() {
    await delay();
    return [
      { provider: 'quickbooks' as const, connected: true, accountName: 'QuickBooks Online', accountIdentifier: 'Mikes Plumbing Ltd', lastSyncAt: '2025-06-20T10:00:00Z' },
      { provider: 'xero' as const, connected: false, accountName: null, accountIdentifier: null, lastSyncAt: null },
      { provider: 'stripe' as const, connected: true, accountName: 'Stripe', accountIdentifier: '...4242', lastSyncAt: '2025-06-20T15:00:00Z' },
      { provider: 'twilio' as const, connected: true, accountName: 'Twilio', accountIdentifier: '+44 20 7946 0123', lastSyncAt: '2025-06-19T08:00:00Z' },
      { provider: 'whatsapp' as const, connected: true, accountName: 'WhatsApp Business', accountIdentifier: '+44 20 7946 0123', lastSyncAt: '2025-06-18T12:00:00Z' },
      { provider: 'google_reviews' as const, connected: true, accountName: 'Google Business', accountIdentifier: 'Mikes Plumbing', lastSyncAt: '2025-06-20T06:00:00Z' },
    ];
  },
};

export { mockTenant, mockUsers };
