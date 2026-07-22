import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { Contact, Customer } from '@/types';

const contactKeys = {
  all: ['contacts'] as const,
  detail: (id: string) => ['contact', id] as const,
};

export function toCustomer(raw: Record<string, unknown>): Customer {
  const name = String(raw.name ?? '');
  const [firstName, ...rest] = name.split(' ');
  const lastName = rest.join(' ') || '';
  return {
    id: String(raw.id),
    firstName,
    lastName,
    email: (raw.email as string | null) ?? null,
    phone: (raw.phone as string | null) ?? '',
    address: (raw.address as string | null) ?? null,
    postcode: (raw.postcode as string | null) ?? null,
    propertyType: (raw.propertyType as Customer['propertyType']) ?? null,
    sourceChannel: (raw.sourceChannel as Customer['sourceChannel']) ?? 'manual',
    lifetimeValue: Number(raw.lifetimeValue ?? 0),
    reviewCount: Number(raw.reviewCount ?? 0),
    averageRating: raw.averageRating != null ? Number(raw.averageRating) : null,
    notes: (raw.notes as string | null) ?? null,
    avatarUrl: (raw.avatarUrl as string | null) ?? null,
    createdAt: String(raw.createdAt),
  };
}

export function useContacts() {
  return useQuery<Customer[], ApiError>({
    queryKey: contactKeys.all,
    queryFn: async () => {
      const data = await api.get<Record<string, unknown>[]>('/contacts');
      return data.map(toCustomer);
    },
  });
}

export function useContact(id: string) {
  return useQuery<Customer, ApiError>({
    queryKey: contactKeys.detail(id),
    queryFn: async () => {
      const data = await api.get<Record<string, unknown>>(`/contacts/${id}`);
      return toCustomer(data);
    },
    enabled: Boolean(id),
  });
}

export type CreateContactPayload = Omit<
  Contact,
  'id' | 'createdAt' | 'updatedAt' | 'averageRating' | 'notes' | 'avatarUrl'
> &
  Partial<Pick<Contact, 'averageRating' | 'notes' | 'avatarUrl'>>;

function toBackendContactCreate(data: CreateContactPayload): Record<string, unknown> {
  return {
    name: `${data.firstName} ${data.lastName}`.trim(),
    email: data.email,
    phone: data.phone,
    address: data.address,
    postcode: data.postcode,
    notes: data.notes,
  };
}

export function useCreateContact() {
  const queryClient = useQueryClient();

  return useMutation<Customer, ApiError, CreateContactPayload>({
    mutationFn: async (data) => {
      const raw = await api.post<Record<string, unknown>>('/contacts', toBackendContactCreate(data));
      return toCustomer(raw);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: contactKeys.all });
    },
  });
}

export function useUpdateContact() {
  const queryClient = useQueryClient();

  return useMutation<Customer, ApiError, { id: string; data: Partial<Contact> }>({
    mutationFn: async ({ id, data }) => {
      const payload: Record<string, unknown> = {};
      if ('firstName' in data || 'lastName' in data) {
        const first = (data.firstName as string | undefined) ?? '';
        const last = (data.lastName as string | undefined) ?? '';
        payload.name = `${first} ${last}`.trim();
      }
      if ('email' in data) payload.email = data.email;
      if ('phone' in data) payload.phone = data.phone;
      if ('address' in data) payload.address = data.address;
      if ('postcode' in data) payload.postcode = data.postcode;
      if ('notes' in data) payload.notes = data.notes;
      const raw = await api.patch<Record<string, unknown>>(`/contacts/${id}`, payload);
      return toCustomer(raw);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contactKeys.all });
      queryClient.invalidateQueries({ queryKey: contactKeys.detail(variables.id) });
    },
  });
}

export function useDeleteContact() {
  const queryClient = useQueryClient();

  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete(`/contacts/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: contactKeys.all });
    },
  });
}
