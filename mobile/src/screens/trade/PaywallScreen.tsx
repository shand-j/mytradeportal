import { useEffect } from "react";
import { View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { SUBSCRIPTION_TIER_KEY, useBillingPlans, useSubscription, type PlanKey } from "../../api/billing";
import { useAuth } from "../../contexts/AuthContext";
import { useBusiness } from "../../theme/ThemeProvider";
import { usePaywallStore } from "../../stores/paywallStore";
import { FALLBACK_PLANS } from "../onboarding/steps/PlanPaymentStep";

const PLAN_NAMES: Record<PlanKey, string> = {
  starter: "Starter",
  pro: "Pro",
  business: "Business",
};

/**
 * Shown when the backend answers 402 subscription_required: the tenant has no
 * active subscription. App Store Guideline 3.1.1 — the app carries no purchase
 * flow, so this screen explains the gate, shows read-only plan pricing and
 * points to the website as plain text (never a link). useSubscription polls
 * while incomplete, so a web subscription releases the paywall automatically.
 */
export function PaywallScreen() {
  const router = useRouter();
  const setRequired = usePaywallStore((s) => s.setRequired);
  const { logout } = useAuth();
  const { setBusiness } = useBusiness();
  const { data: subscription } = useSubscription();
  const plansQuery = useBillingPlans();

  const planKey = subscription?.planKey ?? "pro";
  const tierKey = subscription ? SUBSCRIPTION_TIER_KEY[planKey] : undefined;
  const catalog = plansQuery.data ?? FALLBACK_PLANS;
  const tier = tierKey ? catalog.find((p) => p.key === tierKey) : undefined;

  // useSubscription polls every 3s while status is "incomplete".
  const active = subscription && ["trialing", "active", "past_due"].includes(subscription.status);
  useEffect(() => {
    if (active) {
      setRequired(false);
      router.replace("/(trade)/dashboard");
    }
  }, [active, router, setRequired]);

  const signInAgain = () => {
    setBusiness(null);
    logout();
    router.replace("/");
  };

  return (
    <Screen>
      <View className="flex-1 items-center justify-center gap-4">
        <View className="h-16 w-16 items-center justify-center rounded-full bg-accent-50">
          <Icon name="shield" size={28} color="#0F1E26" />
        </View>
        <Text variant="title" weight="bold" align="center">
          Subscription required
        </Text>
        <Text variant="body" color="secondary" align="center">
          This feature needs an active My Trade Portal subscription
          {subscription ? ` — your ${PLAN_NAMES[planKey]} plan isn't active yet` : ""}. Subscribe on
          our website and this screen clears itself as soon as your plan activates.
        </Text>
        {tier && (
          <Text variant="caption" color="secondary" align="center">
            {tier.name}: £{tier.monthlyPriceGbp}/month or £{tier.annualPriceGbp}/year —{" "}
            {tier.trialDays}-day free trial included.
          </Text>
        )}
        <Text variant="body" weight="semibold" align="center">
          Subscribe at mytradeportal.co.uk
        </Text>
        <Button testID="paywall-sign-in" title="Sign in" onPress={signInAgain} />
        <Text variant="caption" color="secondary" align="center">
          Already subscribed with a different account? Sign in again to switch.
        </Text>
      </View>
    </Screen>
  );
}
