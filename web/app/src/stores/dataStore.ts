import { create } from 'zustand';
import type { KpiData, Quote, Job, Customer, Invoice, Appointment, Review, Activity, Notification, ServiceOffering, DemandForecast } from '@/types';
import * as services from '@/lib/mock/services';

interface DataState {
  // Dashboard
  kpiData: KpiData | null;
  revenueChart: { labels: string[]; revenue: number[]; target: number[] } | null;
  serviceBreakdown: { service: string; percentage: number; revenue: number; color: string }[] | null;
  recentActivity: Activity[];

  // Lists
  quotes: Quote[];
  jobs: Job[];
  customers: Customer[];
  invoices: Invoice[];
  appointments: Appointment[];
  reviews: Review[];
  notifications: Notification[];
  services: ServiceOffering[];

  // AI
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  aiQuotePerformance: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  voiceAnalytics: any;
  demandForecast: DemandForecast | null;

  // Settings
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  businessSettings: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  integrations: any[];

  // Loading states
  isLoading: Record<string, boolean>;

  // Actions
  fetchDashboard: () => Promise<void>;
  fetchQuotes: () => Promise<void>;
  fetchJobs: () => Promise<void>;
  fetchCustomers: () => Promise<void>;
  fetchInvoices: () => Promise<void>;
  fetchAppointments: () => Promise<void>;
  fetchReviews: () => Promise<void>;
  fetchNotifications: () => Promise<void>;
  fetchAiInsights: () => Promise<void>;
  fetchSettings: () => Promise<void>;
  getQuoteById: (id: string) => Quote | undefined;
  getJobById: (id: string) => Job | undefined;
  getCustomerById: (id: string) => Customer | undefined;
  getInvoiceById: (id: string) => Invoice | undefined;
  getUnreadCount: () => number;
}

export const useDataStore = create<DataState>((set, get) => ({
  kpiData: null,
  revenueChart: null,
  serviceBreakdown: null,
  recentActivity: [],
  quotes: [],
  jobs: [],
  customers: [],
  invoices: [],
  appointments: [],
  reviews: [],
  notifications: [],
  services: [],
  aiQuotePerformance: null,
  voiceAnalytics: null,
  demandForecast: null,
  businessSettings: null,
  integrations: [],
  isLoading: {},

  fetchDashboard: async () => {
    set(s => ({ isLoading: { ...s.isLoading, dashboard: true } }));
    const [kpi, chart, services_, activity] = await Promise.all([
      services.mockDashboardService.getKpiData(),
      services.mockDashboardService.getRevenueChart('month'),
      services.mockDashboardService.getServiceBreakdown(),
      services.mockDashboardService.getRecentActivity(),
    ]);
    set({ kpiData: kpi, revenueChart: chart, serviceBreakdown: services_, recentActivity: activity, isLoading: { ...get().isLoading, dashboard: false } });
  },

  fetchQuotes: async () => {
    set(s => ({ isLoading: { ...s.isLoading, quotes: true } }));
    const data = await services.mockQuoteService.listQuotes();
    set({ quotes: data.quotes, isLoading: { ...get().isLoading, quotes: false } });
  },

  fetchJobs: async () => {
    set(s => ({ isLoading: { ...s.isLoading, jobs: true } }));
    const data = await services.mockJobService.listJobs();
    set({ jobs: data.jobs, isLoading: { ...get().isLoading, jobs: false } });
  },

  fetchCustomers: async () => {
    set(s => ({ isLoading: { ...s.isLoading, customers: true } }));
    const data = await services.mockCustomerService.listCustomers();
    set({ customers: data.customers, isLoading: { ...get().isLoading, customers: false } });
  },

  fetchInvoices: async () => {
    set(s => ({ isLoading: { ...s.isLoading, invoices: true } }));
    const data = await services.mockInvoiceService.listInvoices();
    set({ invoices: data.invoices, isLoading: { ...get().isLoading, invoices: false } });
  },

  fetchAppointments: async () => {
    set(s => ({ isLoading: { ...s.isLoading, appointments: true } }));
    const data = await services.mockCalendarService.getAppointments();
    set({ appointments: data, isLoading: { ...get().isLoading, appointments: false } });
  },

  fetchReviews: async () => {
    set(s => ({ isLoading: { ...s.isLoading, reviews: true } }));
    const data = await services.mockReviewService.listReviews();
    set({ reviews: data.reviews, isLoading: { ...get().isLoading, reviews: false } });
  },

  fetchNotifications: async () => {
    const data = await services.mockNotificationService.listNotifications();
    set({ notifications: data });
  },

  fetchAiInsights: async () => {
    set(s => ({ isLoading: { ...s.isLoading, ai: true } }));
    const [perf, voice, forecast] = await Promise.all([
      services.mockAiService.getQuotePerformance(),
      services.mockAiService.getVoiceAnalytics(),
      services.mockAiService.getDemandForecast(),
    ]);
    set({ aiQuotePerformance: perf, voiceAnalytics: voice, demandForecast: forecast, isLoading: { ...get().isLoading, ai: false } });
  },

  fetchSettings: async () => {
    set(s => ({ isLoading: { ...s.isLoading, settings: true } }));
    const [biz, svcs, ints] = await Promise.all([
      services.mockSettingsService.getBusinessSettings(),
      services.mockSettingsService.listServices(),
      services.mockSettingsService.getIntegrations(),
    ]);
    set({ businessSettings: biz, services: svcs, integrations: ints, isLoading: { ...get().isLoading, settings: false } });
  },

  getQuoteById: (id) => get().quotes.find(q => q.id === id),
  getJobById: (id) => get().jobs.find(j => j.id === id),
  getCustomerById: (id) => get().customers.find(c => c.id === id),
  getInvoiceById: (id) => get().invoices.find(i => i.id === id),
  getUnreadCount: () => get().notifications.filter(n => !n.read).length,
}));
