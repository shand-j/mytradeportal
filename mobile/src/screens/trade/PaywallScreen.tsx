import { useEffect, useState } from "react";
import { Linking, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { createBillingCheckout, isSubscriptionActive, useSubscription, type PlanKey } from "../../api/billing";
import { config } from "../../lib/config";
import { usePaywallStore } from "../../stores/paywallStore";

const PLAN_NAMES: Record<PlanKey, string> = {
  starter: "Starter",
  pro: "Pro",
  business: "Business",
};

/**
 * Shown when the backend answers 402 subscription_required: the tenant reached
 * the plan step but the checkout was never completed (or lapsed). Completing
 * checkout flips the subscription via the Paddle webhook; useSubscription
 * polls while incomplete and we release the paywall automatically.
 */
export function PaywallScreen() {
  const router = useRouter();
  const setRequired = usePaywallStore((s) => s.setRequired);
  // Poll while inactive so a web checkout (webhook → status flip) releases
  // the paywall automatically.
  const { data: subscription } = useSubscription({ pollWhileInactive: true });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const planKey = subscription?.planKey ?? "pro";

  // Mirrors the server gate (is_subscription_active): a "trialing" row whose
  // trial_ends_at has passed is NOT active. Releasing on a lapsed trial is
  // the paywall↔dashboard loop — the next gated call 402s and the global gate
  // routes straight back here.
  const active = isSubscriptionActive(subscription);
  const trialExpired =
    subscription?.status === "trial_expired" ||
    (subscription?.status === "trialing" &&
      subscription.trialEndsAt != null &&
      new Date(subscription.trialEndsAt).getTime() <= Date.now());
  useEffect(() => {
    if (active) {
      setRequired(false);
      router.replace("/(trade)/dashboard");
    }
  }, [active, router, setRequired]);

  const completeCheckout = () => {
    setError(null);
    setLoading(true);
    void (async () => {
      try {
        const checkoutPageUrl = `${config.apiBaseUrl}/billing/checkout-page`;
        const { checkoutUrl } = await createBillingCheckout(planKey, checkoutPageUrl);
        const opened = await Linking.canOpenURL(checkoutUrl);
        if (opened) {
          await Linking.openURL(checkoutUrl);
        } else {
          setError("Couldn't open the checkout. Try again.");
        }
      } catch {
        setError("Couldn't start the checkout. Check your connection and try again.");
      } finally {
        setLoading(false);
      }
    })();
  };

  return (
    <Screen>
      <View className="flex-1 items-center justify-center gap-4">
        <View className="h-16 w-16 items-center justify-center rounded-full bg-accent-50">
          <Icon name="shield" size={28} color="#0F1E26" />
        </View>
        <Text variant="title" weight="bold" align="center">
          {trialExpired ? "Your free trial has ended" : "Finish setting up your plan"}
        </Text>
        <Text variant="body" color="secondary" align="center">
          {trialExpired
            ? `Subscribe to the ${PLAN_NAMES[planKey]} plan to keep using My Trade Portal. Free during beta — no charge on your card until we come out of beta.`
            : `Your ${PLAN_NAMES[planKey]} plan checkout wasn't completed. Free during beta — no charge on your card until we come out of beta.`}
        </Text>
        {error && (
          <View className="rounded-2xl bg-red-50 p-4">
            <Text variant="caption" color="warning">
              {error}
            </Text>
          </View>
        )}
        <Button
          testID="paywall-complete-checkout"
          title={loading ? "Opening secure checkout…" : "Complete secure checkout"}
          onPress={completeCheckout}
          disabled={loading}
        />
        <Text variant="caption" color="secondary">
          Secure payment processed by Paddle
        </Text>
      </View>
    </Screen>
  );
}
