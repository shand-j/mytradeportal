import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { Appointment, AppointmentStatus, AvailabilitySlot } from '@/types';

import { toCustomer } from './contacts';

const appointmentKeys = {
  all: ['appointments'] as const,
  detail: (id: string) => ['appointment', id] as const,
  availability: (date: string) => ['appointments', 'availability', date] as const,
};

export function toAppointment(raw: Record<string, unknown>): Appointment {
  // The API serves start_at/end_at (camelized to startAt/endAt by the client)
  // and does not embed a customer object on appointments.
  const customer = raw.customer
    ? toCustomer(raw.customer as Record<string, unknown>)
    : undefined;
  const title = String(raw.title ?? '');

  return {
    id: String(raw.id),
    customerId: String(raw.customerId ?? raw.contactId ?? raw.contact_id ?? ''),
    customer,
    jobId: (raw.jobId ?? raw.job_id ?? null) as string | null,
    title,
    startTime: String(raw.startTime ?? raw.startAt ?? raw.start_at ?? ''),
    endTime: String(raw.endTime ?? raw.endAt ?? raw.end_at ?? ''),
    serviceType: String(raw.serviceType ?? raw.service_type ?? ''),
    propertyAddress: String(raw.propertyAddress ?? raw.property_address ?? raw.address ?? ''),
    status: (raw.status as AppointmentStatus) ?? 'scheduled',
    technicianName: (raw.technicianName ?? raw.technician_name ?? null) as string | null,
  };
}

function toBackendAppointment(data: Partial<Appointment> & { customerId?: string }) {
  // The API client decamelizes keys, so startAt → start_at etc.
  const payload: Record<string, unknown> = {};
  if (data.customerId != null) payload.contactId = data.customerId;
  if (data.jobId !== undefined) payload.jobId = data.jobId;
  if (data.title != null) payload.title = data.title;
  if (data.startTime != null) payload.startAt = data.startTime;
  if (data.endTime != null) payload.endAt = data.endTime;
  if (data.status != null) payload.status = data.status;
  if (data.propertyAddress != null) payload.address = data.propertyAddress;
  if (data.technicianName != null) payload.notes = data.technicianName;
  return payload;
}

export function useAppointments() {
  return useQuery<Appointment[], ApiError>({
    queryKey: appointmentKeys.all,
    queryFn: async () => {
      const data = await api.get<Record<string, unknown>[]>('/appointments');
      return data.map(toAppointment);
    },
  });
}

export function useAppointment(id: string) {
  return useQuery<Appointment, ApiError>({
    queryKey: appointmentKeys.detail(id),
    queryFn: async () => {
      const data = await api.get<Record<string, unknown>>(`/appointments/${id}`);
      return toAppointment(data);
    },
    enabled: Boolean(id),
  });
}

export type CreateAppointmentPayload = Omit<Appointment, 'id' | 'customer'> & {
  customerId: string;
};

export function useCreateAppointment() {
  const queryClient = useQueryClient();

  return useMutation<Appointment, ApiError, CreateAppointmentPayload>({
    mutationFn: async (data) => {
      const raw = await api.post<Record<string, unknown>>('/appointments', toBackendAppointment(data));
      return toAppointment(raw);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
    },
  });
}

export function useUpdateAppointment() {
  const queryClient = useQueryClient();

  return useMutation<Appointment, ApiError, { id: string; data: Partial<Appointment> }>({
    mutationFn: async ({ id, data }) => {
      const raw = await api.patch<Record<string, unknown>>(`/appointments/${id}`, toBackendAppointment(data));
      return toAppointment(raw);
    },
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
