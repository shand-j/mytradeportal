import type { DashboardData, AiInsightsData, ReviewStats, Tenant } from '@/types';

export const mockTenant: Tenant = {
  id: 'tenant-001',
  name: 'Watts Electrical',
  slug: 'watts-electrical',
  logoUrl: '/logo-icon.jpg',
  primaryColor: '#D4650A',
  secondaryColor: '#2563EB',
  hourlyLaborRate: 75,
  markupPercentage: 30,
  minimumCharge: 150,
  vatRate: 20,
  email: 'tom@wattselectrical.co.uk',
  phone: '020 7946 0456',
  website: 'www.wattselectrical.co.uk',
  address: '42 Electric Avenue, London SE14 6QJ',
  planTier: 'professional',
  googlePlaceId: 'ChIJ9876543210',
  createdAt: '2024-01-15T00:00:00Z',
};

export const mockDashboardData: DashboardData = {
  kpi: {
    revenueThisMonth: 24500,
    revenueChange: 12,
    activeJobs: 8,
    jobsCapacity: 12,
    pendingQuotes: 5,
    pendingQuotesValue: 18400,
    quotesExpiringSoon: 2,
    averageRating: 4.8,
    reviewCount: 42,
  },
  revenueChart: {
    labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
    revenue: [4000, 5500, 7000, 8000],
    target: [4500, 6000, 7500, 8500],
  },
  serviceBreakdown: [
    { service: 'Full Rewire', percentage: 40, revenue: 9800, color: '#D4650A' },
    { service: 'EV Charger', percentage: 30, revenue: 7350, color: '#16A34A' },
    { service: 'Smart Home', percentage: 20, revenue: 4900, color: '#2563EB' },
    { service: 'Emergency', percentage: 10, revenue: 2450, color: '#7C3AED' },
  ],
  recentActivity: [
    {
      id: 'act-001',
      type: 'quote_accepted',
      title: 'Quote accepted',
      description: 'Q-2025-0042 — £10,404',
      entityType: 'quote',
      entityId: 'quote-001',
      createdAt: '2025-06-15T10:23:00Z',
    },
  ],
  voiceStats: {
    callsToday: 4,
    resolutionRate: 92,
    quotesFromVoice: 3,
    avgCallDuration: '3m 24s',
  },
};

export const mockAiInsightsData: AiInsightsData = {
  aiQuotePerformance: {
    totalGenerated: 48,
    acceptanceRate: 68,
    averageValue: 3200,
    averageGenerationTime: 4.2,
    monthlyData: [
      { month: 'Jan', aiQuotes: 5, manualQuotes: 8, aiAcceptance: 60, manualAcceptance: 45 },
      { month: 'Feb', aiQuotes: 6, manualQuotes: 7, aiAcceptance: 65, manualAcceptance: 50 },
    ],
  },
  voiceAnalytics: {
    totalCalls: 124,
    averageDuration: '4m 12s',
    resolutionRate: 88,
    totalRevenue: 15600,
    recentCalls: [],
  },
  demandForecast: {
    predictions: [
      { week: '2025-W25', predictedJobs: 8, confidence: 0.85 },
      { week: '2025-W26', predictedJobs: 10, confidence: 0.8 },
    ],
    insight: 'Demand is expected to rise by 15% over the next two weeks.',
  },
};

export const mockReviewStats: ReviewStats = {
  averageRating: 4.7,
  totalReviews: 42,
  thisMonthCount: 6,
  thisMonthChange: 12,
  responseRate: 90,
  platformBreakdown: [
    { platform: 'google', count: 38, average: 4.7 },
    { platform: 'trustpilot', count: 4, average: 4.5 },
  ],
};
