import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

import { TopBar } from './TopBar';
import { useUiStore } from '@/stores/uiStore';

vi.mock('@/lib/api/hooks', () => ({
  useFeatureFlags: () => ({ data: {} }),
}));

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location-display">{location.pathname}</div>;
}

const renderWithRouter = (ui: ReactNode) => render(
  <MemoryRouter initialEntries={['/']}>
    <Routes>
      <Route
        path="*"
        element={(
          <>
            {ui}
            <LocationDisplay />
          </>
        )}
      />
    </Routes>
  </MemoryRouter>
);

describe('TopBar', () => {
  beforeEach(() => {
    useUiStore.setState({
      notificationOpen: false,
      currentPageTitle: 'Dashboard',
    });
  });

  it('displays the current page title', () => {
    useUiStore.setState({ currentPageTitle: 'Quotes' });
    renderWithRouter(<TopBar />);
    expect(screen.getByText('Quotes')).toBeInTheDocument();
  });

  it('toggles the notifications panel', async () => {
    const user = userEvent.setup();
    renderWithRouter(<TopBar />);

    expect(screen.queryByText('Notifications')).not.toBeInTheDocument();

    await user.click(screen.getByLabelText('Notifications'));
    expect(screen.getByText('Notifications')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Notifications'));
    expect(screen.queryByText('Notifications')).not.toBeInTheDocument();
  });

  it('disables search and refreshes the page', async () => {
    const user = userEvent.setup();
    const originalLocation = window.location;
    const reload = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, reload },
    });

    try {
      renderWithRouter(<TopBar />);
      expect(screen.getByRole('button', { name: 'Search (coming soon)' })).toBeDisabled();
      await user.click(screen.getByRole('button', { name: 'Refresh page' }));
      expect(reload).toHaveBeenCalledOnce();
    } finally {
      Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
    }
  });

  it('closes notifications when navigating from "View all notifications"', async () => {
    const user = userEvent.setup();
    renderWithRouter(<TopBar />);

    await user.click(screen.getByLabelText('Notifications'));
    expect(screen.getByText('Notifications')).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: 'View all notifications' }));
    expect(screen.queryByText('Notifications')).not.toBeInTheDocument();
    expect(screen.getByTestId('location-display')).toHaveTextContent('/settings');
  });
});
