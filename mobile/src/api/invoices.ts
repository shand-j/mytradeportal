import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/apiClient";
import { Invoice, InvoiceStatus } from "../types";
import { ApiContact } from "./quotes";

export type ApiInvoiceLineItem = {
  id: string;
  description: string;
  quantity: string;
  unitPrice: string;
  total: string;
};

/** Camelized InvoiceRead (subset the app uses). */
export type ApiInvoice = {
  id: string;
  quoteId: string | null;
  jobId: string | null;
  invoiceNumber: string;
  status: string;
  issueDate: string;
  dueDate: string | null;
  subtotal: string;
  vatAmount: string;
  total: string;
  paidAt: string | null;
  lineItems: ApiInvoiceLineItem[];
  customer: ApiContact;
};

const STATUS_MAP: Record<string, InvoiceStatus> = {
  draft: "draft",
  sent: "sent",
  paid: "paid",
  overdue: "overdue",
  cancelled: "draft",
};

/** Map a backend invoice into the app's display `Invoice` shape. */
export function mapInvoice(a: ApiInvoice): Invoice {
  const title = a.lineItems?.[0]?.description || a.invoiceNumber;
  const isIssued = a.status !== "draft";
  return {
    id: a.id,
    quoteId: a.quoteId ?? "",
    customerName: a.customer?.name ?? "Customer",
    title,
    amount: parseFloat(a.total) || 0,
    status: STATUS_MAP[a.status] ?? "sent",
    dueDate: a.dueDate ?? a.issueDate,
    sentAt: isIssued ? a.issueDate : undefined,
    paidAt: a.paidAt ?? undefined,
  };
}

export async function fetchInvoices(): Promise<ApiInvoice[]> {
  return api.get<ApiInvoice[]>("/invoices");
}

export async function fetchInvoice(id: string): Promise<ApiInvoice> {
  return api.get<ApiInvoice>(`/invoices/${id}`);
}

export type CreateInvoiceInput = {
  contactId: string;
  jobId?: string;
  quoteId?: string;
  lineItems: { description: string; quantity: number; unitPrice: number }[];
};

/**
 * Create a draft invoice (POST /invoices) without sending it — the electrician
 * reviews and sends from the invoice page. When `quoteId` is set and no line
 * items are given, the backend builds the lines from the quote.
 */
export async function createInvoice(input: CreateInvoiceInput): Promise<ApiInvoice> {
  return api.post<ApiInvoice>("/invoices", {
    contactId: input.contactId,
    jobId: input.jobId,
    quoteId: input.quoteId,
    ...(input.lineItems.length > 0 ? { lineItems: input.lineItems } : {}),
  });
}

/**
 * Create an invoice (from a completed job's line items) and immediately mark it
 * sent, so it lands ready to be paid. Returns the created invoice.
 */
export async function createAndSendInvoice(input: CreateInvoiceInput): Promise<ApiInvoice> {
  const created = await api.post<ApiInvoice>("/invoices", {
    contactId: input.contactId,
    jobId: input.jobId,
    quoteId: input.quoteId,
    lineItems: input.lineItems,
  });
  return api.post<ApiInvoice>(`/invoices/${created.id}/send`);
}

export async function markInvoicePaid(id: string): Promise<ApiInvoice> {
  return api.post<ApiInvoice>(`/invoices/${id}/mark-paid`);
}

/** Mark an invoice sent and notify/email the customer (also used for reminders). */
export async function sendInvoice(id: string): Promise<ApiInvoice> {
  return api.post<ApiInvoice>(`/invoices/${id}/send`);
}

export type UpdateInvoiceInput = {
  lineItems?: { description: string; quantity: number; unitPrice: number }[];
  dueDate?: string;
  notes?: string;
  status?: string;
};

/** Update an invoice; the backend replaces line items and recalculates totals. */
export async function updateInvoice(id: string, input: UpdateInvoiceInput): Promise<ApiInvoice> {
  return api.patch<ApiInvoice>(`/invoices/${id}`, input);
}

/** Invoices list for the trade Invoices screen. */
export function useInvoicesList() {
  const query = useQuery({
    queryKey: ["invoices"],
    queryFn: fetchInvoices,
  });

  return {
    invoices: (query.data ?? []).map(mapInvoice),
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}

/** A single invoice by id, mapped to the app `Invoice` shape. */
export function useInvoice(id: string | undefined) {
  const query = useQuery({
    queryKey: ["invoice", id],
    queryFn: () => fetchInvoice(id as string),
    enabled: !!id,
  });

  return {
    invoice: query.data ? mapInvoice(query.data) : undefined,
    /** Raw API invoice (line items, VAT amounts) for edit flows. */
    apiInvoice: query.data,
    isConnected: query.isSuccess,
    isLoading: !!id && query.isLoading,
  };
}

/** Mutation: mark an invoice paid and refresh the invoice + revenue caches. */
export function useMarkInvoicePaid() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => markInvoicePaid(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["invoices"] });
      qc.invalidateQueries({ queryKey: ["invoice", id] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

/** Mutation: send (or re-send/remind) an invoice and refresh the caches. */
export function useSendInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => sendInvoice(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["invoices"] });
      qc.invalidateQueries({ queryKey: ["invoice", id] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

/** Mutation: update an invoice's line items and refresh the caches. */
export function useUpdateInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateInvoiceInput }) =>
      updateInvoice(id, input),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["invoices"] });
      qc.invalidateQueries({ queryKey: ["invoice", id] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
