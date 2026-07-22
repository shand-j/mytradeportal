import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen } from '@testing-library/react';

import { Sidebar } from './Sidebar';
import { renderWithProviders } from '@/test/test-utils';
import { useAuthStore } from '@/stores/authStore';
import type { User } from '@/types';

vi.mock('@/lib/api/hooks', () => ({
  useQuotes: () => ({ data: [] }),
  useInvoices: () => ({ data: [] }),
}));

const adminUser: User = {
  id: 'u1',
  tenantId: 't1',
  fullName: 'Alice Admin',
  email: 'admin@demo.local',
  phone: null,
  role: 'admin',
  avatarUrl: null,
  isActive: true,
};

const technicianUser: User = {
  id: 'u2',
  tenantId: 't1',
  fullName: 'Tom Technician',
  email: 'tech@demo.local',
  phone: null,
  role: 'technician',
  avatarUrl: null,
  isActive: true,
};

describe('Sidebar', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });

  it('renders all navigation items for an admin user', () => {
    useAuthStore.setState({ user: adminUser });
    renderWithProviders(<Sidebar />);

    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('AI Insights')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.getByText('Alice Admin')).toBeInTheDocument();
  });

  it('hides admin-only items for a technician user', () => {
    useAuthStore.setState({ user: technicianUser });
    renderWithProviders(<Sidebar />);

    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Jobs')).toBeInTheDocument();
    expect(screen.queryByText('AI Insights')).not.toBeInTheDocument();
    expect(screen.queryByText('Settings')).not.toBeInTheDocument();
    expect(screen.getByText('Tom Technician')).toBeInTheDocument();
  });
});
