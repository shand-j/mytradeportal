import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';

import { TopBar } from './TopBar';
import { useUiStore } from '@/stores/uiStore';

vi.mock('@/lib/api/hooks', () => ({
  useFeatureFlags: () => ({ data: {} }),
}));

const renderWithRouter = (ui: ReactNode) => render(<MemoryRouter>{ui}</MemoryRouter>);

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
});
