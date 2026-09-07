import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ReactElement } from 'react';

import { Calendar } from './Calendar';
import {
  useAppointments,
  useContacts,
  useCreateAppointment,
  useUpdateAppointment,
  useDeleteAppointment,
  useAvailability,
} from '@/lib/api/hooks';
import { renderPage, resetStores, createTestQueryClient } from '@/test/test-utils';
import { mockAppointments } from '@/lib/mock/data/appointments';
import { mockCustomers } from '@/lib/mock/data/customers';

const defaultMutations = {
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  isPending: false,
  isIdle: true,
  isSuccess: false,
  isError: false,
  reset: vi.fn(),
  error: null,
  data: undefined,
  status: 'idle',
  failureCount: 0,
  failureReason: null,
  submittedAt: 0,
};

vi.mock('@/lib/api/hooks', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api/hooks')>();
  return {
    ...original,
    useAppointments: vi.fn(() => ({ data: undefined, isLoading: true, error: null })),
    useContacts: vi.fn(() => ({ data: [], isLoading: false, error: null })),
    useCreateAppointment: vi.fn(() => defaultMutations),
    useUpdateAppointment: vi.fn(() => defaultMutations),
    useDeleteAppointment: vi.fn(() => defaultMutations),
    useAvailability: vi.fn(() => ({ data: [], isLoading: false, error: null })),
  };
});

describe('Calendar', () => {
  beforeEach(() => {
    resetStores();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2025-06-23T12:00:00Z'));

    vi.mocked(useAppointments).mockReturnValue({ data: mockAppointments, isLoading: false, error: null });
    vi.mocked(useContacts).mockReturnValue({ data: mockCustomers, isLoading: false, error: null });
    vi.mocked(useCreateAppointment).mockReturnValue(defaultMutations);
    vi.mocked(useUpdateAppointment).mockReturnValue(defaultMutations);
    vi.mocked(useDeleteAppointment).mockReturnValue(defaultMutations);
    vi.mocked(useAvailability).mockReturnValue({ data: [], isLoading: false, error: null });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders a loading skeleton', () => {
    vi.mocked(useAppointments).mockReturnValue({ data: undefined, isLoading: true, error: null });
    const { container } = renderPage(<Calendar />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders an error message', () => {
    vi.mocked(useAppointments).mockReturnValue({ data: undefined, isLoading: false, error: new Error('boom') });
    renderPage(<Calendar />);
    expect(screen.getByText('Failed to load appointments')).toBeInTheDocument();
  });

  it('renders the calendar and appointment content', () => {
    renderPage(<Calendar />);
    expect(screen.getByText('June 2025')).toBeInTheDocument();
    expect(screen.getByText('Smart Home Installation')).toBeInTheDocument();
  });

  it('navigates to the previous and next month', async () => {
    const user = userEvent.setup();
    renderPage(<Calendar />);

    const buttons = screen.getAllByRole('button');
    const [prev, next] = buttons.filter(b => b.className.includes('w-8 h-8'));

    await user.click(next);
    expect(screen.getByText('July 2025')).toBeInTheDocument();

    await user.click(prev);
    await user.click(prev);
    expect(screen.getByText('May 2025')).toBeInTheDocument();
  });

  function renderAtRoute(ui: ReactElement, route: string) {
    return render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route path="/calendar/:view?" element={ui} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it('renders the week view for /calendar/week with appointments in time slots', () => {
    renderAtRoute(<Calendar />, '/calendar/week');

    expect(screen.getByText('Week of 23 Jun 2025')).toBeInTheDocument();
    // Time grid 07:00–19:00.
    expect(screen.getByText('7:00')).toBeInTheDocument();
    expect(screen.getByText('19:00')).toBeInTheDocument();
    // appt-001 starts Mon 2025-06-23 09:00 → rendered as a positioned block.
    expect(screen.getByText(/09:00–17:00 Smart Home Installation/)).toBeInTheDocument();
    expect(screen.getByText(/14:00–16:00 Emergency — RCD Fault/)).toBeInTheDocument();
  });

  it('renders the day view for /calendar/day as a single time column', () => {
    renderAtRoute(<Calendar />, '/calendar/day');

    expect(screen.getByText('Monday, 23 June 2025')).toBeInTheDocument();
    expect(screen.getByText(/09:00–17:00 Smart Home Installation/)).toBeInTheDocument();
    // An appointment on the next day must not appear in the day view.
    expect(screen.queryByText(/EICR & Remedial Works/)).not.toBeInTheDocument();
  });

  it('switches views via the Month/Week/Day buttons', async () => {
    const user = userEvent.setup();
    renderAtRoute(<Calendar />, '/calendar');

    await user.click(screen.getByRole('button', { name: 'Week' }));
    expect(screen.getByText('Week of 23 Jun 2025')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Day' }));
    expect(screen.getByText('Monday, 23 June 2025')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Month' }));
    expect(screen.getByText('June 2025')).toBeInTheDocument();
  });

  it('navigates the day view by single days', async () => {
    const user = userEvent.setup();
    renderAtRoute(<Calendar />, '/calendar/day');

    const buttons = screen.getAllByRole('button');
    const [, next] = buttons.filter(b => b.className.includes('w-8 h-8'));
    await user.click(next);
    expect(screen.getByText('Tuesday, 24 June 2025')).toBeInTheDocument();
  });

  it('opens and closes the new appointment dialog', async () => {
    const user = userEvent.setup();
    renderPage(<Calendar />);

    await user.click(screen.getByRole('button', { name: /new appointment/i }));
    expect(screen.getByRole('heading', { name: 'New Appointment' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByRole('heading', { name: 'New Appointment' })).not.toBeInTheDocument();
  });
});
