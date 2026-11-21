import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen } from '@testing-library/react';

import { Sidebar } from './Sidebar';
import { renderWithProviders } from '@/test/test-utils';
import { useAuthStore } from '@/stores/authStore';
import { useUiStore } from '@/stores/uiStore';
import type { User } from '@/types';

vi.mock('@/lib/api/hooks', () => ({
  useQuotes: () => ({ data: [] }),
  useInvoices: () => ({ data: [] }),
  useFeatureFlags: () => ({ data: {} }),
  useSettings: () => ({ data: undefined }),
}));

vi.mock('@/lib/api/auth', () => ({
  authService: {
    login: vi.fn(),
    logout: vi.fn().mockResolvedValue(undefined),
    me: vi.fn().mockResolvedValue(null),
  },
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
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(() => ({
      matches: false,
      media: '',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
    useUiStore.setState({
      sidebarCollapsed: false,
      notificationOpen: false,
      toasts: [],
      currentPageTitle: 'Dashboard',
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

  it('shows account and logout controls in collapsed sidebar', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(() => ({
      matches: true,
      media: '',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));
    useAuthStore.setState({ user: adminUser, isAuthenticated: true });
    useUiStore.setState({ sidebarCollapsed: true });
    renderWithProviders(<Sidebar />);

    expect(screen.getByRole('link', { name: 'Account settings' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Logout' })).toBeInTheDocument();
  });
});
