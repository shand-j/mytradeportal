import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test/test-utils';
import { AiInsights } from './AiInsights';

const mockUseAiInsights = vi.fn();
const mockUseFeatureFlags = vi.fn(() => ({
  data: { voiceAiInsights: true, demandForecasting: true, externalIntegrations: false },
  isLoading: false,
  error: null,
}));

vi.mock('@/lib/api/hooks', () => ({
  useAiInsights: () => mockUseAiInsights(),
  useFeatureFlags: () => mockUseFeatureFlags(),
}));

const mockData = {
  aiQuotePerformance: {
    totalGenerated: 124,
    acceptanceRate: 68,
    averageValue: 1240,
    averageGenerationTime: 12,
    editRate: 0.35,
    avgPriceDriftPct: 4.2,
    monthlyData: [
      { month: 'Jan', aiQuotes: 10, manualQuotes: 4 },
      { month: 'Feb', aiQuotes: 12, manualQuotes: 5 },
    ],
  },
  voiceAnalytics: {
    totalCalls: 86,
    averageDuration: '3m 12s',
    resolutionRate: 92,
    totalRevenue: 18400,
  },
  demandForecast: {
    predictions: [
      { week: 'W1', predictedJobs: 8 },
      { week: 'W2', predictedJobs: 10 },
    ],
    insight: 'Demand is expected to rise 12% next month.',
  },
};

describe('AiInsights', () => {
  beforeEach(() => {
    mockUseFeatureFlags.mockReturnValue({
      data: { voiceAiInsights: true, demandForecasting: true, externalIntegrations: false },
      isLoading: false,
      error: null,
    });
  });

  it('renders a loading skeleton', () => {
    mockUseAiInsights.mockReturnValue({ data: undefined, isLoading: true, error: null });
    renderWithProviders(<AiInsights />);
    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('renders an error message', () => {
    mockUseAiInsights.mockReturnValue({ data: mockData, isLoading: false, error: new Error('boom') });
    renderWithProviders(<AiInsights />);
    expect(screen.getByText(/failed to load ai insights/i)).toBeInTheDocument();
  });

  it('renders the error message instead of a skeleton when the request fails with no data', () => {
    mockUseAiInsights.mockReturnValue({ data: undefined, isLoading: false, error: new Error('boom') });
    renderWithProviders(<AiInsights />);
    expect(screen.getByText(/failed to load ai insights/i)).toBeInTheDocument();
    expect(document.querySelectorAll('.animate-pulse').length).toBe(0);
  });

  it('renders insights from mock data', () => {
    mockUseAiInsights.mockReturnValue({ data: mockData, isLoading: false, error: null });
    renderWithProviders(<AiInsights />);
    expect(screen.getByText('AI Quote Performance')).toBeInTheDocument();
    expect(screen.getByText('Powered by AI')).toBeInTheDocument();
    expect(screen.getByText('Voice Agent Activity')).toBeInTheDocument();
    expect(screen.getByText('Demand Forecast')).toBeInTheDocument();
    expect(screen.getByText('124')).toBeInTheDocument();
    expect(screen.getByText('68%')).toBeInTheDocument();
    expect(screen.getByText('86')).toBeInTheDocument();
    expect(screen.getByText(/demand is expected to rise/i)).toBeInTheDocument();
  });

  it('renders the edit rate and price drift stats when present', () => {
    mockUseAiInsights.mockReturnValue({ data: mockData, isLoading: false, error: null });
    renderWithProviders(<AiInsights />);
    expect(screen.getByText('AI Drafts Edited')).toBeInTheDocument();
    expect(screen.getByText('35%')).toBeInTheDocument();
    expect(screen.getByText('Avg Price Adjustment')).toBeInTheDocument();
    expect(screen.getByText('4.2%')).toBeInTheDocument();
  });

  it('hides the edit rate and price drift stats when null', () => {
    const withoutNewStats = {
      ...mockData,
      aiQuotePerformance: { ...mockData.aiQuotePerformance, editRate: null, avgPriceDriftPct: null },
    };
    mockUseAiInsights.mockReturnValue({ data: withoutNewStats, isLoading: false, error: null });
    renderWithProviders(<AiInsights />);
    expect(screen.getByText('AI Quote Performance')).toBeInTheDocument();
    expect(screen.queryByText('AI Drafts Edited')).not.toBeInTheDocument();
    expect(screen.queryByText('Avg Price Adjustment')).not.toBeInTheDocument();
  });

  it('hides voice analytics and demand forecast when their feature flags are off', () => {
    mockUseFeatureFlags.mockReturnValue({ data: {}, isLoading: false, error: null });
    mockUseAiInsights.mockReturnValue({ data: mockData, isLoading: false, error: null });
    renderWithProviders(<AiInsights />);
    expect(screen.getByText('AI Quote Performance')).toBeInTheDocument();
    expect(screen.queryByText('Voice Agent Activity')).not.toBeInTheDocument();
    expect(screen.queryByText('Demand Forecast')).not.toBeInTheDocument();
  });
});
