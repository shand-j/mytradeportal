import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Calendar } from './Calendar';
import {
  useAppointments,
  useContacts,
  useCreateAppointment,
  useUpdateAppointment,
  useDeleteAppointment,
  useAvailability,
} from '@/lib/api/hooks';
import { renderPage, resetStores } from '@/test/test-utils';
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

  it('opens and closes the new appointment dialog', async () => {
    const user = userEvent.setup();
    renderPage(<Calendar />);

    await user.click(screen.getByRole('button', { name: /new appointment/i }));
    expect(screen.getByRole('heading', { name: 'New Appointment' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByRole('heading', { name: 'New Appointment' })).not.toBeInTheDocument();
  });
});
