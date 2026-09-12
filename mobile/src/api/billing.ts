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
