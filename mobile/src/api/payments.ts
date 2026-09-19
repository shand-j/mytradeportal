import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/apiClient";

/** Camelized PaymentStatusRead from GET /payments/status. */
export type PaymentsStatus = {
  stripeConfigured: boolean;
  connected: boolean;
  stripeAccountId: string | null;
  detailsSubmitted: boolean;
  chargesEnabled: boolean;
  payoutsEnabled: boolean;
  onboardingComplete: boolean;
  /** Tenant-level default for offering card payment on new invoices. */
  acceptCardDefault: boolean;
};

export type ConnectStripeRead = {
  onboardingUrl: string;
};

export async function getPaymentsStatus(): Promise<PaymentsStatus> {
  return api.get<PaymentsStatus>("/payments/status");
}

/**
 * Create (or reuse) the tenant's Stripe Express account and return its hosted
 * onboarding URL. The tradie completes onboarding in the in-app browser, then
 * Stripe redirects to the return URL — the app passes deep links
 * (mtp://payments/...) so the flow lands back inside the app.
 */
export async function connectStripe(input?: {
  returnUrl?: string;
  refreshUrl?: string;
}): Promise<ConnectStripeRead> {
  return api.post<ConnectStripeRead>("/payments/connect", input ?? {});
}

/** Set the tenant-level default for offering card payment on new invoices. */
export async function updatePaymentsSettings(input: {
  acceptCardDefault: boolean;
}): Promise<PaymentsStatus> {
  return api.patch<PaymentsStatus>("/payments/settings", input);
}

export function usePaymentsStatus() {
  return useQuery({
    queryKey: ["payments", "status"],
    queryFn: getPaymentsStatus,
  });
}

export function useUpdatePaymentsSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: updatePaymentsSettings,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["payments", "status"] });
      qc.invalidateQueries({ queryKey: ["invoices"] });
    },
  });
}
