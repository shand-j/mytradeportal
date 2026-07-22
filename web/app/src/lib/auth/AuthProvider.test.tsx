import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { AuthProvider } from './AuthProvider';
import { useAuthStore } from '@/stores/authStore';
import type { User } from '@/types';

const mockUser: User = {
  id: 'u1',
  tenantId: 't1',
  fullName: 'Admin User',
  email: 'admin@demo.local',
  phone: null,
  role: 'admin',
  avatarUrl: null,
  isActive: true,
};

const me = vi.fn();

vi.mock('@/lib/api/auth', () => ({
  authService: {
    login: vi.fn(),
    logout: vi.fn(),
    me: () => me(),
  },
}));

function StoreReader() {
  const { user, isAuthenticated, isLoading } = useAuthStore();
  return (
    <div>
      <span data-testid="loading">{isLoading ? 'loading' : 'ready'}</span>
      <span data-testid="authenticated">{isAuthenticated ? 'yes' : 'no'}</span>
      <span data-testid="user">{user?.fullName ?? 'none'}</span>
    </div>
  );
}

describe('AuthProvider', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: true,
    });
    me.mockReset();
  });

  it('fetches /auth/me on mount and sets the user', async () => {
    me.mockResolvedValueOnce(mockUser);

    render(
      <AuthProvider>
        <StoreReader />
      </AuthProvider>,
    );

    expect(screen.getByTestId('loading')).toHaveTextContent('loading');

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('ready');
    });

    expect(screen.getByTestId('authenticated')).toHaveTextContent('yes');
    expect(screen.getByTestId('user')).toHaveTextContent('Admin User');
    expect(me).toHaveBeenCalledTimes(1);
  });

  it('handles errors by clearing the user', async () => {
    me.mockRejectedValueOnce(new Error('Not authenticated'));

    render(
      <AuthProvider>
        <StoreReader />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('ready');
    });

    expect(screen.getByTestId('authenticated')).toHaveTextContent('no');
    expect(screen.getByTestId('user')).toHaveTextContent('none');
  });
});
