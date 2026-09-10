import { useEffect, useState } from "react";
import { Linking, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { createBillingCheckout, useSubscription, type PlanKey } from "../../api/billing";
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
  const { data: subscription } = useSubscription();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const planKey = subscription?.planKey ?? "pro";

  // useSubscription polls every 3s while status is "incomplete".
  const active = subscription && ["trialing", "active", "past_due"].includes(subscription.status);
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
        <View className="h-16 w-16 items-center justify-center rounded-full bg-blue-50">
          <Icon name="shield" size={28} color="#0F1E26" />
        </View>
        <Text variant="title" weight="bold" align="center">
          Finish setting up your plan
        </Text>
        <Text variant="body" color="secondary" align="center">
          Your {PLAN_NAMES[planKey]} plan checkout wasn't completed. Free during beta — no charge on
          your card until we come out of beta.
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
