import { describe, it, expect, vi, beforeEach } from 'vitest';
import userEvent from '@testing-library/user-event';
import { screen, waitFor } from '@testing-library/react';

import { Login } from './Login';
import { renderWithProviders } from '@/test/test-utils';
import { authService } from '@/lib/api/auth';
import { useAuthStore } from '@/stores/authStore';
import type { User } from '@/types';

vi.mock('@/lib/api/auth', () => ({
  authService: {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn(),
  },
}));

describe('Login', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
    vi.mocked(authService.login).mockReset();
    vi.mocked(authService.me).mockRejectedValue(new Error('Not authenticated'));
  });

  it('submits email and password through authService.login', async () => {
    const user: User = {
      id: 'u1',
      tenantId: 't1',
      fullName: 'Admin User',
      email: 'admin@demo.local',
      phone: null,
      role: 'admin',
      avatarUrl: null,
      isActive: true,
    };

    vi.mocked(authService.login).mockResolvedValueOnce(user);

    renderWithProviders(<Login />);

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    await userEvent.clear(emailInput);
    await userEvent.type(emailInput, 'admin@demo.local');
    await userEvent.type(passwordInput, 'password123');
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(authService.login).toHaveBeenCalledTimes(1);
      expect(authService.login).toHaveBeenCalledWith({
        email: 'admin@demo.local',
        password: 'password123',
      });
    });
  });

  it('displays an error message when login fails', async () => {
    vi.mocked(authService.login).mockRejectedValueOnce(new Error('Invalid credentials'));

    renderWithProviders(<Login />);

    const passwordInput = screen.getByLabelText(/password/i);
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    await userEvent.type(passwordInput, 'wrong');
    await userEvent.click(submitButton);

    expect(await screen.findByText(/invalid credentials/i)).toBeInTheDocument();
  });
});
