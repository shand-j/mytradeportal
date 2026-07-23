import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import App from './App';
import { createTestQueryClient, resetStores } from '@/test/test-utils';
import { useAuthStore } from '@/stores/authStore';
import * as hooks from '@/lib/api/hooks';

import type { User } from '@/types';

const mockUser = vi.hoisted<User>(() => ({
  id: 'user-001',
  tenantId: 'tenant-001',
  fullName: 'Tom Watts',
  email: 'tom@wattselectrical.co.uk',
  phone: '07700 900111',
  role: 'admin',
  avatarUrl: null,
  isActive: true,
}));

const defaultMutation = vi.hoisted(() => () => ({
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  isPending: false,
  isIdle: true,
  isSuccess: false,
  isError: false,
  reset: vi.fn(),
  error: null,
  data: undefined,
  status: 'idle',
  failureCount: 0,
  failureReason: null,
  submittedAt: 0,
}));

const mockDashboardData = vi.hoisted(() => ({
  kpi: {
    revenueThisMonth: 12000,
    revenueChange: 8,
    activeJobs: 3,
    jobsCapacity: 8,
    pendingQuotes: 4,
    pendingQuotesValue: 5400,
    quotesExpiringSoon: 1,
    averageRating: 4.8,
    reviewCount: 24,
  },
  revenueChart: {
    labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
    revenue: [2000, 3000, 2500, 4500],
    target: [2500, 2500, 2500, 2500],
  },
  serviceBreakdown: [],
  recentActivity: [],
  voiceStats: {
    callsToday: 4,
    resolutionRate: 92,
    quotesFromVoice: 3,
    avgCallDuration: '3m 24s',
  },
}));

const mockAiInsightsData = vi.hoisted(() => ({
  aiQuotePerformance: {
    totalGenerated: 12,
    acceptanceRate: 68,
    averageValue: 2450,
    averageGenerationTime: 4.2,
    monthlyData: [
      { month: 'Jan', aiQuotes: 2, manualQuotes: 5, aiAcceptance: 50, manualAcceptance: 40 },
    ],
  },
  voiceAnalytics: {
    totalCalls: 48,
    averageDuration: '3m 12s',
    resolutionRate: 92,
    totalRevenue: 8500,
    recentCalls: [],
  },
  demandForecast: {
    predictions: [{ week: 'W1', predictedJobs: 5, confidence: 0.8 }],
    insight: 'Demand is steady.',
  },
}));

const mockReviewStats = vi.hoisted(() => ({
  averageRating: 4.8,
  totalReviews: 24,
  thisMonthCount: 3,
  thisMonthChange: 12,
  responseRate: 95,
  platformBreakdown: [],
}));

vi.mock('@/lib/api/auth', () => ({
  authService: {
    me: vi.fn().mockResolvedValue(mockUser),
    login: vi.fn(),
    logout: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('@/lib/api/hooks', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api/hooks')>();
  return {
    ...original,
    useDashboard: vi.fn(() => ({ data: mockDashboardData, isLoading: false, error: null })),
    useQuotes: vi.fn(() => ({ data: [], isLoading: false, error: null })),
    useInvoices: vi.fn(() => ({ data: [], isLoading: false, error: null })),
    useJobs: vi.fn(() => ({ data: [], isLoading: false, error: null })),
    useContacts: vi.fn(() => ({ data: [], isLoading: false, error: null })),
    useAppointments: vi.fn(() => ({ data: [], isLoading: false, error: null })),
    useAvailability: vi.fn(() => ({ data: [], isLoading: false, error: null })),
    useReviews: vi.fn(() => ({ data: [], isLoading: false, error: null })),
    useReviewStats: vi.fn(() => ({ data: mockReviewStats, isLoading: false, error: null })),
    useAiInsights: vi.fn(() => ({ data: mockAiInsightsData, isLoading: false, error: null })),
    useFeatureFlags: vi.fn(() => ({ data: {}, isLoading: false, error: null })),
    useSettings: vi.fn(() => ({ data: undefined, isLoading: false, error: null })),
    useUpdateSettings: vi.fn(defaultMutation),
    useCreateQuote: vi.fn(defaultMutation),
    useUpdateQuote: vi.fn(defaultMutation),
    useSendQuote: vi.fn(defaultMutation),
    useApproveQuote: vi.fn(defaultMutation),
    useRejectQuote: vi.fn(defaultMutation),
    useGenerateQuote: vi.fn(defaultMutation),
    useRefineQuote: vi.fn(defaultMutation),
    useConvertQuoteToInvoice: vi.fn(defaultMutation),
    useDeleteQuote: vi.fn(defaultMutation),
    useQuoteBoq: vi.fn(() => ({ data: null, isLoading: false, error: null })),
    useCreateJob: vi.fn(defaultMutation),
    useUpdateJob: vi.fn(defaultMutation),
    useTransitionJobStatus: vi.fn(defaultMutation),
    useDeleteJob: vi.fn(defaultMutation),
    useCreateInvoice: vi.fn(defaultMutation),
    useUpdateInvoice: vi.fn(defaultMutation),
    useSendInvoice: vi.fn(defaultMutation),
    useMarkInvoicePaid: vi.fn(defaultMutation),
    useCancelInvoice: vi.fn(defaultMutation),
    useDeleteInvoice: vi.fn(defaultMutation),
    useCreateContact: vi.fn(defaultMutation),
    useUpdateContact: vi.fn(defaultMutation),
    useDeleteContact: vi.fn(defaultMutation),
    useCreateReview: vi.fn(defaultMutation),
    useCreateAppointment: vi.fn(defaultMutation),
    useUpdateAppointment: vi.fn(defaultMutation),
    useDeleteAppointment: vi.fn(defaultMutation),
    useAppointment: vi.fn(() => ({ data: undefined, isLoading: false, error: null })),
    useContact: vi.fn(() => ({ data: undefined, isLoading: false, error: null })),
    useJob: vi.fn(() => ({ data: undefined, isLoading: false, error: null })),
    useInvoice: vi.fn(() => ({ data: undefined, isLoading: false, error: null })),
  };
});

const { mockQuotes } = await import('@/lib/mock/data/quotes');
const { mockJobs } = await import('@/lib/mock/data/jobs');
const { mockCustomers } = await import('@/lib/mock/data/customers');
const { mockInvoices } = await import('@/lib/mock/data/invoices');
const { mockAppointments } = await import('@/lib/mock/data/appointments');
const { mockReviews } = await import('@/lib/mock/data/reviews');
const { mockTenant } = await import('@/lib/mock/data/tenant');

function renderApp(initialEntries: string[] = ['/']) {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter initialEntries={initialEntries}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('App routing', () => {
  beforeEach(() => {
    resetStores();
    useAuthStore.setState({ user: mockUser, isAuthenticated: true, isLoading: false });
    vi.mocked(hooks.useQuotes).mockReturnValue({ data: mockQuotes, isLoading: false, error: null });
    vi.mocked(hooks.useInvoices).mockReturnValue({ data: mockInvoices, isLoading: false, error: null });
    vi.mocked(hooks.useJobs).mockReturnValue({ data: mockJobs, isLoading: false, error: null });
    vi.mocked(hooks.useContacts).mockReturnValue({ data: mockCustomers, isLoading: false, error: null });
    vi.mocked(hooks.useAppointments).mockReturnValue({ data: mockAppointments, isLoading: false, error: null });
    vi.mocked(hooks.useReviews).mockReturnValue({ data: mockReviews, isLoading: false, error: null });
    vi.mocked(hooks.useSettings).mockReturnValue({ data: mockTenant, isLoading: false, error: null });
  });

  it('renders the login page for unauthenticated users', async () => {
    useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
    renderApp(['/']);
    expect(await screen.findByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('lands on the dashboard when authenticated', async () => {
    renderApp(['/']);
    expect(await screen.findByText(/Revenue This Month/i)).toBeInTheDocument();
    // Voice AI blocks stay hidden while the feature flag defaults off.
    expect(screen.queryByText(/Voice AI Agent is live/i)).not.toBeInTheDocument();
  });

  it('navigates through sidebar links without a real backend', async () => {
    const user = userEvent.setup();
    renderApp(['/']);

    expect(await screen.findByText(/Revenue This Month/i)).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: /quotes/i }));
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /quotes/i })).toBeInTheDocument();
    });
    expect(screen.getByText('Q-2025-0042')).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: /jobs/i }));
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /jobs/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('link', { name: /customers/i }));
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /customers/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('link', { name: /invoices/i }));
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /invoices/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('link', { name: /settings/i }));
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /settings/i })).toBeInTheDocument();
    });
  });
});
