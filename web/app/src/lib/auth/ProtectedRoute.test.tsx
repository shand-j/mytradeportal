import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { ProtectedRoute } from './ProtectedRoute';
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

function renderWithRouter(initialEntries: string[], authenticated: boolean, loading: boolean) {
  useAuthStore.setState({
    user: authenticated ? mockUser : null,
    isAuthenticated: authenticated,
    isLoading: loading,
  });

  // Prevent the AuthProvider from making real network calls when it is included.
  vi.stubGlobal('fetch', vi.fn());

  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/protected" element={<div>protected content</div>} />
        </Route>
        <Route path="/login" element={<div>login page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows a loading spinner while auth state is loading', () => {
    const { container } = renderWithRouter(['/protected'], false, true);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
    expect(screen.queryByText('protected content')).not.toBeInTheDocument();
  });

  it('redirects to /login when the user is not authenticated', () => {
    renderWithRouter(['/protected'], false, false);
    expect(screen.getByText('login page')).toBeInTheDocument();
    expect(screen.queryByText('protected content')).not.toBeInTheDocument();
  });

  it('renders the protected outlet when the user is authenticated', () => {
    renderWithRouter(['/protected'], true, false);
    expect(screen.getByText('protected content')).toBeInTheDocument();
    expect(screen.queryByText('login page')).not.toBeInTheDocument();
  });
});
