import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test/test-utils';
import { AiInsights } from './AiInsights';

const mockUseAiInsights = vi.fn();

vi.mock('@/lib/api/hooks', () => ({
  useAiInsights: (...args: any[]) => mockUseAiInsights(...args),
}));

const mockData = {
  aiQuotePerformance: {
    totalGenerated: 124,
    acceptanceRate: 68,
    averageValue: 1240,
    averageGenerationTime: 12,
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

  it('renders insights from mock data', () => {
    mockUseAiInsights.mockReturnValue({ data: mockData, isLoading: false, error: null });
    renderWithProviders(<AiInsights />);
    expect(screen.getByText('AI Quote Performance')).toBeInTheDocument();
    expect(screen.getByText('Voice Agent Activity')).toBeInTheDocument();
    expect(screen.getByText('Demand Forecast')).toBeInTheDocument();
    expect(screen.getByText('124')).toBeInTheDocument();
    expect(screen.getByText('68%')).toBeInTheDocument();
    expect(screen.getByText('86')).toBeInTheDocument();
    expect(screen.getByText(/demand is expected to rise/i)).toBeInTheDocument();
  });
});
