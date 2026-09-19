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

/** Public landing origin hosting the Stripe deep-link bounce page. */
const LANDING_BASE_URL = "https://www.mytradeportal.co.uk";

/**
 * Wrap an app deep link (mtp://...) in the https bounce page URL. Stripe's
 * AccountLink API rejects non-http(s) return/refresh URLs, so onboarding
 * returns via the landing page, which immediately navigates to the deep
 * link — the in-app auth-session browser intercepts it and closes back into
 * the app.
 */
export function stripeBounceUrl(next: string): string {
  return `${LANDING_BASE_URL}/payments/stripe-bounce?next=${encodeURIComponent(next)}`;
}

export async function getPaymentsStatus(): Promise<PaymentsStatus> {
  return api.get<PaymentsStatus>("/payments/status");
}

/**
 * Create (or reuse) the tenant's Stripe Express account and return its hosted
 * onboarding URL. The tradie completes onboarding in the in-app browser, then
 * Stripe redirects to the return URL — https bounce URLs wrapping the app's
 * deep links (mtp://payments/...) so the flow lands back inside the app.
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
