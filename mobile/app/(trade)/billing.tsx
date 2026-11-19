import { useRouter } from "expo-router";
import { ScrollView, View } from "react-native";
import { Button } from "../../src/components/ui/Button";
import { Header } from "../../src/components/ui/Header";
import { Screen } from "../../src/components/ui/Screen";
import { Text } from "../../src/components/ui/Text";
import { SubscriptionCard } from "../../src/components/trade/SubscriptionCard";
import { useSubscription } from "../../src/api/billing";
import { PlanPaymentStep } from "../../src/screens/onboarding/steps/PlanPaymentStep";

/**
 * Billing route. App Store Guideline 3.1.1: no purchase surface in-app.
 * A tenant that already has a subscription row (active, trialing, cancelled,
 * …) sees a read-only status view — current plan, status, trial/renewal
 * dates, and plain-text manage-on-web copy (never a link, never a checkout).
 * A brand-new tenant (no subscription row yet) sees the read-only plan list
 * with the "I've subscribed — continue" pattern. useSubscription keeps its
 * 3s polling while a subscription is "incomplete", so a web checkout that
 * finishes while this screen is open flips the status automatically.
 */
export default function BillingRoute() {
  const router = useRouter();
  const { data: subscription, isLoading } = useSubscription();

  return (
    <Screen>
      <Header title="Subscription" onBack={() => router.back()} />
      <View className="flex-1 pt-2">
        {isLoading ? (
          <Text variant="body" color="secondary">
            Loading your subscription…
          </Text>
        ) : subscription ? (
          <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
            <View className="gap-4 pb-6">
              <Text variant="title" weight="bold">
                Your subscription
              </Text>
              <SubscriptionCard subscription={subscription} />
              <Button testID="billing-done" title="Done" onPress={() => router.back()} />
            </View>
          </ScrollView>
        ) : (
          <PlanPaymentStep onNext={() => router.back()} />
        )}
      </View>
    </Screen>
  );
}
