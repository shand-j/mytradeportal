import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/apiClient";

export type CustomerInvoiceLineItem = {
  id: string;
  description: string;
  quantity: string;
  unitPrice: string;
  total: string;
};

/** Camelized CustomerInvoiceRead from GET /customer/invoices. */
export type CustomerInvoice = {
  id: string;
  invoiceNumber: string;
  status: string;
  issueDate: string;
  dueDate: string | null;
  subtotal: string;
  vatRate: string;
  vatAmount: string;
  total: string;
  paidAt: string | null;
  notes: string | null;
  lineItems: CustomerInvoiceLineItem[];
  businessName: string;
  businessLogoUrl: string | null;
  businessPrimaryColor: string;
  /** Stripe /pay page URL when the tenant takes card payments; null otherwise. */
  paymentUrl: string | null;
};

export type CustomerInvoicePay = {
  paymentUrl: string;
};

/** Invoices sent to the authenticated customer (backend hides drafts). */
export async function fetchMyInvoices(): Promise<CustomerInvoice[]> {
  return api.get<CustomerInvoice[]>("/customer/invoices");
}

/** A single customer-visible invoice with line items and business branding. */
export async function fetchMyInvoice(id: string): Promise<CustomerInvoice> {
  return api.get<CustomerInvoice>(`/customer/invoices/${id}`);
}

/** Mint a Stripe /pay page URL so the customer can pay the invoice by card. */
export async function payMyInvoice(id: string): Promise<CustomerInvoicePay> {
  return api.post<CustomerInvoicePay>(`/customer/invoices/${id}/pay`);
}

/** The logged-in customer's invoice list. */
export function useMyInvoices() {
  const query = useQuery({
    queryKey: ["my-invoices"],
    queryFn: fetchMyInvoices,
  });

  return {
    invoices: query.data ?? [],
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}

/** A single customer invoice by id. */
export function useMyInvoice(id: string | undefined) {
  const query = useQuery({
    queryKey: ["my-invoice", id],
    queryFn: () => fetchMyInvoice(id as string),
    enabled: !!id,
  });

  return {
    invoice: query.data,
    isConnected: query.isSuccess,
    isLoading: !!id && query.isLoading,
  };
}

/** Mutation: mint a Stripe pay link for an invoice and refresh the caches. */
export function usePayMyInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => payMyInvoice(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["my-invoices"] });
      qc.invalidateQueries({ queryKey: ["my-invoice", id] });
    },
  });
}
