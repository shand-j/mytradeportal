import { useState } from "react";
import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Text } from "../../../components/ui/Text";
import { StripeConnectCard } from "../../../components/trade/StripeConnectCard";
import { usePaymentsStatus } from "../../../api/payments";

type CardPaymentsStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

/**
 * The "Will you take card payments?" gate (#188). Opting in runs Stripe
 * Connect onboarding straight from this screen (in-app browser — the same
 * StripeConnectCard Settings → Payments shows); opting out continues the
 * wizard and leaves activation for later via Settings.
 */
export function CardPaymentsStep({ data, onNext }: CardPaymentsStepProps) {
  const statusQuery = usePaymentsStatus();
  const [wantsCards, setWantsCards] = useState<boolean | null>(
    (data?.takeCardPayments as boolean | undefined) ?? null
  );
  const status = statusQuery.data;
  const connected = Boolean(status?.connected);

  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Will you take card payments?
        </Text>
        <Text variant="body" color="secondary">
          Let customers pay invoices online by card with Stripe. It takes a few minutes to set up —
          or you can do it any time later from Settings → Payments.
        </Text>

        <View className="flex-row gap-2">
          <View className="flex-1">
            <Button
              testID="onboarding-card-payments-yes"
              title="Yes, take cards"
              variant={wantsCards ? "primary" : "outline"}
              onPress={() => setWantsCards(true)}
            />
          </View>
          <View className="flex-1">
            <Button
              testID="onboarding-card-payments-no"
              title="Not now"
              variant={wantsCards === false ? "primary" : "outline"}
              onPress={() => setWantsCards(false)}
            />
          </View>
        </View>

        {wantsCards && <StripeConnectCard />}

        <Button
          testID="onboarding-card-payments-continue"
          title={wantsCards && !connected ? "Continue without card payments" : "Continue"}
          variant={wantsCards && !connected ? "outline" : "primary"}
          disabled={wantsCards === null}
          onPress={() =>
            onNext({
              takeCardPayments: Boolean(wantsCards),
              stripeConnected: connected,
            })
          }
        />
      </View>
    </ScrollView>
  );
}
