import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { Job } from '@/types';

import { toCustomer } from './contacts';

const jobKeys = {
  all: ['jobs'] as const,
  detail: (id: string) => ['job', id] as const,
};

function toDateTimeLocal(date: string, time: string = '09:00'): string {
  return `${date}T${time}`;
}

function splitDateTime(iso: string | null): { date: string; time: string } {
  if (!iso) return { date: '', time: '' };
  const [date, time] = iso.split('T');
  return { date: date || '', time: time ? time.slice(0, 5) : '' };
}

export function toJob(raw: Record<string, unknown>, quoteTotals?: ReadonlyMap<string, number>): Job {
  const customer = raw.customer ? toCustomer(raw.customer as Record<string, unknown>) : undefined;
  const scheduledStart = String(raw.scheduledStart ?? raw.scheduled_start ?? '');
  const scheduledEnd = String(raw.scheduledEnd ?? raw.scheduled_end ?? '');
  const { date: scheduledDate, time: scheduledTimeStart } = splitDateTime(scheduledStart || null);
  const { time: scheduledTimeEnd } = splitDateTime(scheduledEnd || null);
  const title = String(raw.title ?? raw.reference ?? '');
  const description = String(raw.description ?? '');
  const quoteId = (raw.quoteId ?? raw.quote_id ?? null) as string | null;
  // The API has no job value field; the job's value comes from its linked
  // quote's total when no explicit value is present.
  const explicitValue = raw.value ?? raw.total;
  const value =
    explicitValue != null
      ? Number(explicitValue)
      : (quoteId ? quoteTotals?.get(quoteId) : 0) ?? 0;

  return {
    id: String(raw.id),
    reference: title,
    customerId: String(raw.customerId ?? raw.contactId ?? raw.contact_id ?? ''),
    customer: customer as Job['customer'],
    quoteId,
    status: (raw.status as Job['status']) ?? 'scheduled',
    serviceType: description || title,
    description,
    scheduledDate,
    scheduledTimeStart: scheduledTimeStart || null,
    scheduledTimeEnd: scheduledTimeEnd || null,
    technicianId: (raw.technicianId ?? raw.technician_id ?? null) as string | null,
    technicianName: (raw.technicianName ?? raw.technician_name ?? null) as string | null,
    propertyAddress: String(raw.propertyAddress ?? raw.property_address ?? ''),
    value,
    completionNotes: (raw.completionNotes ?? raw.completion_notes ?? null) as string | null,
    photos: Array.isArray(raw.photos) ? (raw.photos as string[]) : [],
    createdAt: String(raw.createdAt ?? raw.created_at),
  };
}

async function fetchQuoteTotals(): Promise<Map<string, number>> {
  const quotes = await api.get<Record<string, unknown>[]>('/quotes');
  return new Map(quotes.map(q => [String(q.id), Number(q.total ?? 0)]));
}

export function useJobs() {
  return useQuery<Job[], ApiError>({
    queryKey: jobKeys.all,
    queryFn: async () => {
      const [jobs, quoteTotals] = await Promise.all([
        api.get<Record<string, unknown>[]>('/jobs'),
        fetchQuoteTotals(),
      ]);
      return jobs.map(job => toJob(job, quoteTotals));
    },
  });
}

export function useJob(id: string) {
  return useQuery<Job, ApiError>({
    queryKey: jobKeys.detail(id),
    queryFn: async () => {
      const raw = await api.get<Record<string, unknown>>(`/jobs/${id}`);
      const quoteId = (raw.quoteId ?? raw.quote_id ?? null) as string | null;
      let quoteTotals: Map<string, number> | undefined;
      if (quoteId && raw.value == null && raw.total == null) {
        const quote = await api
          .get<Record<string, unknown>>(`/quotes/${quoteId}`)
          .catch(() => null);
        if (quote) quoteTotals = new Map([[String(quote.id), Number(quote.total ?? 0)]]);
      }
      return toJob(raw, quoteTotals);
    },
    enabled: Boolean(id),
  });
}

export type CreateJobPayload = Omit<Job, 'id' | 'createdAt' | 'customer'> & {
  customerId: string;
};

function toBackendJobCreate(data: CreateJobPayload): Record<string, unknown> {
  const description = [data.serviceType, data.propertyAddress, data.description]
    .filter(Boolean)
    .join('\n');
  return {
    contact_id: data.customerId,
    title: data.reference,
    description: description || null,
    scheduled_start: toDateTimeLocal(data.scheduledDate),
    scheduled_end: toDateTimeLocal(data.scheduledDate, '17:00'),
  };
}

export function useCreateJob() {
  const queryClient = useQueryClient();

  return useMutation<Job, ApiError, CreateJobPayload>({
    mutationFn: async (data) => {
      const raw = await api.post<Record<string, unknown>>('/jobs', toBackendJobCreate(data));
      return toJob(raw);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: jobKeys.all });
    },
  });
}

export function useUpdateJob() {
  const queryClient = useQueryClient();

  return useMutation<Job, ApiError, { id: string; data: Partial<Job> }>({
    mutationFn: async ({ id, data }) => {
      const payload: Record<string, unknown> = {};
      if ('serviceType' in data || 'propertyAddress' in data || 'description' in data) {
        payload.description = [data.serviceType, data.propertyAddress, data.description]
          .filter(Boolean)
          .join('\n');
      }
      if ('scheduledDate' in data && data.scheduledDate) {
        payload.scheduled_start = toDateTimeLocal(data.scheduledDate);
        payload.scheduled_end = toDateTimeLocal(data.scheduledDate, '17:00');
      }
      if ('status' in data) payload.status = data.status;
      if ('technicianName' in data) payload.notes = data.technicianName;
      const raw = await api.patch<Record<string, unknown>>(`/jobs/${id}`, payload);
      return toJob(raw);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: jobKeys.all });
      queryClient.invalidateQueries({ queryKey: jobKeys.detail(variables.id) });
    },
  });
}

export type JobTransitionAction = 'start' | 'complete' | 'cancel';

export function useTransitionJobStatus(action: JobTransitionAction) {
  const queryClient = useQueryClient();

  return useMutation<Job, ApiError, string>({
    mutationFn: async (id) => {
      const raw = await api.post<Record<string, unknown>>(`/jobs/${id}/${action}`);
      return toJob(raw);
    },
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: jobKeys.all });
      queryClient.invalidateQueries({ queryKey: jobKeys.detail(id) });
    },
  });
}

export function useDeleteJob() {
  const queryClient = useQueryClient();

  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete(`/jobs/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: jobKeys.all });
    },
  });
}
