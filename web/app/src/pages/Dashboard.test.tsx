import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Dashboard } from './Dashboard';
import { useDashboard } from '@/lib/api/hooks';
import { renderPage, resetStores } from '@/test/test-utils';
import { mockDashboardData } from '@/test/fixtures';

vi.mock('@/lib/api/hooks', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api/hooks')>();
  return {
    ...original,
    useDashboard: vi.fn(() => ({ data: undefined, isLoading: true, error: null })),
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
    expect(screen.getByText('Voice AI Agent is live')).toBeInTheDocument();
  });

  it('responds to a user interaction without crashing', async () => {
    const user = userEvent.setup();
    renderPage(<Dashboard />);

    const button = screen.getByRole('button', { name: /view call log/i });
    await user.click(button);

    expect(screen.getByText('Voice AI Agent is live')).toBeInTheDocument();
  });
});
