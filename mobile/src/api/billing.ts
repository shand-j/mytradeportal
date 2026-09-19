import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/apiClient";

export type PlanKey = "starter" | "pro" | "business";

// Current tier keys from GET /billing/plans. The checkout endpoint still
// speaks the legacy keys until the W2-B Paddle catalog work lands, so plan
// selections are mapped back when creating a checkout.
export type BillingPlanKey = "sole_trader" | "pro" | "team";

export const CHECKOUT_PLAN_KEY: Record<BillingPlanKey, PlanKey> = {
  sole_trader: "starter",
  pro: "pro",
  team: "business",
};

/** Inverse of CHECKOUT_PLAN_KEY — a subscription's legacy plan key → tier. */
export const SUBSCRIPTION_TIER_KEY: Record<PlanKey, BillingPlanKey> = {
  starter: "sole_trader",
  pro: "pro",
  business: "team",
};

export type BillingPlan = {
  key: BillingPlanKey;
  name: string;
  monthlyPriceEnv: string;
  annualPriceEnv: string;
  monthlyPriceGbp: number;
  annualPriceGbp: number;
  aiAllowanceMonthly: number;
  overageBehavior: "block" | "metered";
  overagePricePence: number;
  minSeats: number;
  /** Staff seats included in the tier (max active users + pending invites). */
  seats: number;
  pooledAllowance: boolean;
  featured: boolean;
  trialDays: number;
  trialExtensionDays: number;
  trialExtensionSentAiQuotes: number;
};

export async function getBillingPlans(): Promise<BillingPlan[]> {
  return api.get<BillingPlan[]>("/billing/plans");
}

export function useBillingPlans() {
  return useQuery({
    queryKey: ["billing", "plans"],
    queryFn: getBillingPlans,
    // Static catalog; callers fall back to a local copy on failure, so one
    // retry is plenty and a stale cache is harmless.
    staleTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export type SubscriptionRead = {
  id: string;
  planKey: PlanKey;
  status: "incomplete" | "trialing" | "active" | "past_due" | "paused" | "canceled";
  paddleSubscriptionId: string | null;
  paddleCustomerId: string | null;
  trialEndsAt: string | null;
  currentPeriodStart: string | null;
  currentPeriodEnd: string | null;
  scheduledChangeAction: string | null;
  scheduledChangeAt: string | null;
  canceledAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type BillingCheckoutRead = {
  transactionId: string;
  checkoutUrl: string;
};

export async function createBillingCheckout(
  planKey: PlanKey,
  successUrl?: string
): Promise<BillingCheckoutRead> {
  return api.post<BillingCheckoutRead>("/billing/checkout", {
    planKey,
    successUrl,
  });
}

export async function getSubscription(): Promise<SubscriptionRead | null> {
  return api.get<SubscriptionRead | null>("/billing/subscription");
}

export type BillingPortalSessionRead = {
  portalUrl: string;
};

/** Mint a short-lived Paddle customer-portal URL (manage/cancel subscription). */
export async function createPortalSession(): Promise<BillingPortalSessionRead> {
  return api.post<BillingPortalSessionRead>("/billing/portal-session");
}

export function useSubscription() {
  return useQuery({
    queryKey: ["billing", "subscription"],
    queryFn: getSubscription,
    // A completed Paddle checkout arrives via webhook — poll for a few
    // seconds after the user returns from the checkout URL.
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      if (data.status === "incomplete") return 3000;
      return false;
    },
  });
}

export function useCreateBillingCheckout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ planKey, successUrl }: { planKey: PlanKey; successUrl?: string }) =>
      createBillingCheckout(planKey, successUrl),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["billing", "subscription"] });
    },
  });
}

/**
 * True when the tenant's subscription tier includes more than one staff seat
 * (seat counts come from GET /billing/plans — the per-plan source of truth).
 * False while either query is loading or when there is no subscription, so
 * single-seat tenants never see team-only UI.
 */
export function useMultiSeatPlan(): boolean {
  const subscription = useSubscription();
  const plans = useBillingPlans();
  const planKey = subscription.data?.planKey;
  if (!planKey) return false;
  const tier = plans.data?.find((p) => p.key === SUBSCRIPTION_TIER_KEY[planKey]);
  return (tier?.seats ?? 1) > 1;
}
