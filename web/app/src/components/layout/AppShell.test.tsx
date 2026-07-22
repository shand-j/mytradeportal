import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, useNavigate } from 'react-router-dom';

import { AppShell } from './AppShell';
import { useAuthStore } from '@/stores/authStore';

vi.mock('@/lib/api/hooks', () => ({
  useQuotes: () => ({ data: [], isLoading: false, error: null }),
  useInvoices: () => ({ data: [], isLoading: false, error: null }),
}));

function Home() {
  const navigate = useNavigate();
  return (
    <div>
      <h1>Home Page</h1>
      <button onClick={() => navigate('/other')}>Go to other</button>
    </div>
  );
}

function Other() {
  return <h1>Other Page</h1>;
}

describe('AppShell', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { id: 'u1', tenantId: 't1', fullName: 'Admin', email: 'admin@demo.local', phone: null, role: 'admin', avatarUrl: null, isActive: true },
      isAuthenticated: true,
      isLoading: false,
    });
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  });

  it('renders sidebar, topbar, and outlet content', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Home />} />
            <Route path="/other" element={<Other />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('mytradeportal')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /collapse/i })).toBeInTheDocument();
    expect(screen.getByText('Home Page')).toBeInTheDocument();
  });

  it('scrolls to top when the route changes', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Home />} />
            <Route path="/other" element={<Other />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(window.scrollTo).toHaveBeenCalledWith(0, 0);

    await user.click(screen.getByRole('button', { name: /go to other/i }));
    expect(screen.getByText('Other Page')).toBeInTheDocument();

    expect(window.scrollTo).toHaveBeenLastCalledWith(0, 0);
    expect(window.scrollTo).toHaveBeenCalledWith(0, 0);
  });
});
