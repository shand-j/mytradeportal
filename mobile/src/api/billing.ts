import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";

export type PlanKey = "starter" | "pro" | "business";

// Current tier keys from GET /billing/plans. Subscriptions are created and
// managed on the web (mytradeportal.co.uk) — App Store Guideline 3.1.1 means
// the app carries no purchase flow, so the plan-key mapping below only goes
// one way: a subscription's legacy plan key → its display tier.
export type BillingPlanKey = "sole_trader" | "pro" | "team";

/** A subscription's legacy plan key → tier. */
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
  /** Staff seats included in the plan (sole_trader 1, pro 5, team 15). */
  seats: number;
  /** Active users + pending invites — the count the seat cap gates on. */
  seatsInUse: number;
};

export async function getSubscription(): Promise<SubscriptionRead | null> {
  return api.get<SubscriptionRead | null>("/billing/subscription");
}

export function useSubscription() {
  return useQuery({
    queryKey: ["billing", "subscription"],
    queryFn: getSubscription,
    // A web subscription arrives via the Paddle webhook — poll for a few
    // seconds after the user subscribes on mytradeportal.co.uk and returns.
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      if (data.status === "incomplete") return 3000;
      return false;
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
