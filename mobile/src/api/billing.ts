import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/apiClient";

export type PlanKey = "starter" | "pro" | "business";

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
