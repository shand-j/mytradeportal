import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { Invoice, PaymentMethod } from '@/types';

import { toCustomer } from './contacts';

const invoiceKeys = {
  all: ['invoices'] as const,
  detail: (id: string) => ['invoice', id] as const,
};

export function toInvoice(raw: Record<string, unknown>): Invoice {
  const customer = raw.customer ? toCustomer(raw.customer as Record<string, unknown>) : undefined;
  const status = (raw.status as Invoice['status']) ?? 'draft';
  const total = Number(raw.total ?? 0);
  const amountPaid = status === 'paid' ? total : Number(raw.amountPaid ?? 0);
  const amountDue = Number(raw.amountDue ?? total - amountPaid);

  return {
    id: String(raw.id),
    reference: String(raw.invoiceNumber ?? raw.invoice_number ?? raw.reference ?? ''),
    customerId: String(raw.customerId ?? raw.contactId ?? raw.contact_id ?? ''),
    customer: customer as Invoice['customer'],
    jobId: (raw.jobId ?? raw.job_id ?? null) as string | null,
    quoteId: (raw.quoteId ?? raw.quote_id ?? null) as string | null,
    status,
    lineItems: Array.isArray(raw.lineItems)
      ? (raw.lineItems as Record<string, unknown>[]).map((item) => ({
          id: String(item.id),
          description: String(item.description ?? ''),
          quantity: Number(item.quantity ?? 1),
          unit: String(item.unit ?? 'item'),
          unitPrice: Number(item.unitPrice ?? item.unit_price ?? 0),
          total: Number(item.total ?? item.quantity ?? 1) * Number(item.unitPrice ?? item.unit_price ?? 0),
        }))
      : [],
    subtotal: Number(raw.subtotal ?? 0),
    vatAmount: Number(raw.vatAmount ?? raw.vat_amount ?? 0),
    vatRate: Number(raw.vatRate ?? raw.vat_rate ?? 0.2),
    total,
    amountPaid,
    amountDue,
    issueDate: String(raw.issueDate ?? raw.issue_date ?? ''),
    dueDate: String(raw.dueDate ?? raw.due_date ?? ''),
    paidAt: (raw.paidAt ?? raw.paid_at ?? null) as string | null,
    paymentMethod: (raw.paymentMethod ?? raw.payment_method ?? null) as PaymentMethod | null,
    createdAt: String(raw.createdAt ?? raw.created_at),
  };
}

export function useInvoices() {
  return useQuery<Invoice[], ApiError>({
    queryKey: invoiceKeys.all,
    queryFn: async () => {
      const data = await api.get<Record<string, unknown>[]>('/invoices');
      return data.map(toInvoice);
    },
  });
}

export function useInvoice(id: string) {
  return useQuery<Invoice, ApiError>({
    queryKey: invoiceKeys.detail(id),
    queryFn: async () => {
      const data = await api.get<Record<string, unknown>>(`/invoices/${id}`);
      return toInvoice(data);
    },
    enabled: Boolean(id),
  });
}

export type CreateInvoicePayload = Omit<Invoice, 'id' | 'createdAt' | 'customer'> & {
  customerId: string;
};

function toBackendInvoiceCreate(data: CreateInvoicePayload): Record<string, unknown> {
  return {
    contact_id: data.customerId,
    invoice_number: data.reference,
    due_date: data.dueDate ? `${data.dueDate}T00:00:00` : undefined,
    line_items: data.lineItems.map(({ description, quantity, unitPrice }) => ({
      description,
      quantity,
      unit_price: unitPrice,
    })),
  };
}

export function useCreateInvoice() {
  const queryClient = useQueryClient();

  return useMutation<Invoice, ApiError, CreateInvoicePayload>({
    mutationFn: async (data) => {
      const raw = await api.post<Record<string, unknown>>('/invoices', toBackendInvoiceCreate(data));
      return toInvoice(raw);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: invoiceKeys.all });
    },
  });
}

export function useUpdateInvoice() {
  const queryClient = useQueryClient();

  return useMutation<Invoice, ApiError, { id: string; data: Partial<Invoice> }>({
    mutationFn: async ({ id, data }) => {
      const payload: Record<string, unknown> = {};
      if ('dueDate' in data && data.dueDate) payload.due_date = `${data.dueDate}T00:00:00`;
      if ('status' in data) payload.status = data.status;
      const raw = await api.patch<Record<string, unknown>>(`/invoices/${id}`, payload);
      return toInvoice(raw);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: invoiceKeys.all });
      queryClient.invalidateQueries({ queryKey: invoiceKeys.detail(variables.id) });
    },
  });
}

export function useSendInvoice() {
  const queryClient = useQueryClient();

  return useMutation<Invoice, ApiError, string>({
    mutationFn: async (id) => {
      const raw = await api.post<Record<string, unknown>>(`/invoices/${id}/send`);
      return toInvoice(raw);
    },
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: invoiceKeys.all });
      queryClient.invalidateQueries({ queryKey: invoiceKeys.detail(id) });
    },
  });
}

export interface MarkInvoicePaidVariables {
  id: string;
  paymentMethod?: PaymentMethod;
}

export function useMarkInvoicePaid() {
  const queryClient = useQueryClient();

  return useMutation<Invoice, ApiError, MarkInvoicePaidVariables>({
    mutationFn: async ({ id, paymentMethod }) => {
      const raw = await api.patch<Record<string, unknown>>(`/invoices/${id}/mark-paid`, { paymentMethod });
      return toInvoice(raw);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: invoiceKeys.all });
      queryClient.invalidateQueries({ queryKey: invoiceKeys.detail(variables.id) });
    },
  });
}

export function useCancelInvoice() {
  const queryClient = useQueryClient();

  return useMutation<Invoice, ApiError, string>({
    mutationFn: async (id) => {
      const raw = await api.patch<Record<string, unknown>>(`/invoices/${id}/cancel`);
      return toInvoice(raw);
    },
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: invoiceKeys.all });
      queryClient.invalidateQueries({ queryKey: invoiceKeys.detail(id) });
    },
  });
}

export function useDeleteInvoice() {
  const queryClient = useQueryClient();

  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete(`/invoices/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: invoiceKeys.all });
    },
  });
}
