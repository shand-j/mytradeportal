import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { Appointment, AvailabilitySlot } from '@/types';

const appointmentKeys = {
  all: ['appointments'] as const,
  detail: (id: string) => ['appointment', id] as const,
  availability: (date: string) => ['appointments', 'availability', date] as const,
};

export function useAppointments() {
  return useQuery<Appointment[], ApiError>({
    queryKey: appointmentKeys.all,
    queryFn: () => api.get('/appointments'),
  });
}

export function useAppointment(id: string) {
  return useQuery<Appointment, ApiError>({
    queryKey: appointmentKeys.detail(id),
    queryFn: () => api.get(`/appointments/${id}`),
    enabled: Boolean(id),
  });
}

export type CreateAppointmentPayload = Omit<Appointment, 'id' | 'customer'> & {
  customerId: string;
};

export function useCreateAppointment() {
  const queryClient = useQueryClient();

  return useMutation<Appointment, ApiError, CreateAppointmentPayload>({
    mutationFn: (data) => api.post('/appointments', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
    },
  });
}

export function useUpdateAppointment() {
  const queryClient = useQueryClient();

  return useMutation<Appointment, ApiError, { id: string; data: Partial<Appointment> }>({
    mutationFn: ({ id, data }) => api.patch(`/appointments/${id}`, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      queryClient.invalidateQueries({ queryKey: appointmentKeys.detail(variables.id) });
    },
  });
}

export function useDeleteAppointment() {
  const queryClient = useQueryClient();

  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete(`/appointments/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
    },
  });
}

export function useAvailability(date: string) {
  return useQuery<AvailabilitySlot[], ApiError>({
    queryKey: appointmentKeys.availability(date),
    queryFn: () => api.get(`/appointments/availability?date=${encodeURIComponent(date)}`),
    enabled: Boolean(date),
  });
}
