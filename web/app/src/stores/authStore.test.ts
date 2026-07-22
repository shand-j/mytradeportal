import { describe, it, expect, beforeEach } from 'vitest';
import { act } from '@testing-library/react';

import { useAuthStore } from './authStore';
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

describe('authStore', () => {
  beforeEach(() => {
    act(() => {
      useAuthStore.setState({
        user: null,
        isAuthenticated: false,
        isLoading: false,
      });
    });
  });

  it('starts with no authenticated user', () => {
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it('sets the user and marks authenticated', () => {
    act(() => {
      useAuthStore.getState().setUser(mockUser);
    });

    const state = useAuthStore.getState();
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated).toBe(true);
  });

  it('logs a user in', () => {
    act(() => {
      useAuthStore.getState().login(mockUser);
    });

    const state = useAuthStore.getState();
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated).toBe(true);
    expect(state.isLoading).toBe(false);
  });

  it('logs a user out', () => {
    act(() => {
      useAuthStore.getState().login(mockUser);
      useAuthStore.getState().logout();
    });

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isLoading).toBe(false);
  });

  it('toggles the loading state', () => {
    act(() => {
      useAuthStore.getState().setLoading(true);
    });

    expect(useAuthStore.getState().isLoading).toBe(true);
  });
});
