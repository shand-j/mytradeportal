import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';

import { Dashboard } from './Dashboard';
import { useDashboard } from '@/lib/api/hooks';
import { renderPage, resetStores } from '@/test/test-utils';
import { mockDashboardData } from '@/test/fixtures';

vi.mock('@/lib/api/hooks', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api/hooks')>();
  return {
    ...original,
    useDashboard: vi.fn(() => ({ data: undefined, isLoading: true, error: null })),
    useFeatureFlags: vi.fn(() => ({ data: {}, isLoading: false, error: null })),
  };
});

describe('Dashboard', () => {
  beforeEach(() => {
    resetStores();
    vi.mocked(useDashboard).mockReturnValue({ data: mockDashboardData, isLoading: false, error: null });
  });

  it('renders a loading skeleton', () => {
    vi.mocked(useDashboard).mockReturnValue({ data: undefined, isLoading: true, error: null });
    const { container } = renderPage(<Dashboard />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders an error message', () => {
    vi.mocked(useDashboard).mockReturnValue({ data: mockDashboardData, isLoading: false, error: new Error('boom') });
    renderPage(<Dashboard />);
    expect(screen.getByText('Failed to load dashboard')).toBeInTheDocument();
  });

  it('renders KPI and chart content from mock data', () => {
    renderPage(<Dashboard />);
    expect(screen.getByText('Revenue This Month')).toBeInTheDocument();
    expect(screen.getByText('£24,500')).toBeInTheDocument();
    expect(screen.getByText('Active Jobs')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Week' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Year' })).toBeDisabled();
    expect(screen.getByRole('link', { name: 'View all' })).toHaveAttribute('href', '/jobs');
  });

  it('does not render the removed voice AI blocks', () => {
    renderPage(<Dashboard />);
    expect(screen.queryByText('Voice AI Agent is live')).not.toBeInTheDocument();
    expect(screen.queryByText('Calls Today')).not.toBeInTheDocument();
    expect(screen.queryByText('Voice Quotes')).not.toBeInTheDocument();
  });

  it('renders rating stars when average rating is zero', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: {
        ...mockDashboardData,
        kpi: {
          ...mockDashboardData.kpi,
          averageRating: 0,
          reviewCount: 0,
        },
      },
      isLoading: false,
      error: null,
    });

    renderPage(<Dashboard />);
    expect(screen.getByText('0 reviews')).toBeInTheDocument();
    const customerRatingCard = screen.getByText('Customer Rating').closest('.bg-white');
    expect(customerRatingCard?.querySelectorAll('svg').length).toBeGreaterThanOrEqual(7);
  });
});
