import { useState } from "react";
import { Linking, Pressable, ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";
import { createBillingCheckout, type PlanKey } from "../../../api/billing";
import { NetworkError } from "../../../lib/apiClient";

type Plan = {
  key: PlanKey;
  name: string;
  price: string;
  cadence: string;
  tagline: string;
  features: string[];
  highlighted?: boolean;
};

type PlanPaymentStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

const PLANS: Plan[] = [
  {
    key: "starter",
    name: "Starter",
    price: "£29",
    cadence: "/mo",
    tagline: "For sole traders getting started",
    features: ["Unlimited quote requests", "AI-drafted quotes", "Calendar & jobs"],
  },
  {
    key: "pro",
    name: "Pro",
    price: "£59",
    cadence: "/mo",
    tagline: "For growing electrical businesses",
    features: [
      "Everything in Starter",
      "Invoicing & payments",
      "Team assignment",
      "Branded customer portal",
    ],
    highlighted: true,
  },
  {
    key: "business",
    name: "Business",
    price: "£99",
    cadence: "/mo",
    tagline: "For multi-engineer teams",
    features: ["Everything in Pro", "Up to 10 engineers", "Priority support", "Accounting sync"],
  },
];

export function PlanPaymentStep({ data, onNext }: PlanPaymentStepProps) {
  const initial = (data?.plan as PlanKey | undefined) ?? "pro";
  const [selected, setSelected] = useState<PlanKey>(initial);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const plan = PLANS.find((p) => p.key === selected) ?? PLANS[1];

  const startCheckout = () => {
    setError(null);
    setLoading(true);
    void (async () => {
      try {
        const { checkoutUrl } = await createBillingCheckout(plan.key);
        onNext({ plan: plan.key, checkoutStarted: true });
        // Kick the user out to the Paddle-hosted checkout. The tenant returns
        // via the app scheme when Paddle redirects to success_url — beta uses
        // Paddle's default post-purchase screen.
        const opened = await Linking.canOpenURL(checkoutUrl);
        if (opened) {
          await Linking.openURL(checkoutUrl);
        } else {
          setError("Couldn't open the checkout. Try again.");
        }
      } catch (err) {
        setError(
          err instanceof NetworkError
            ? "Can't reach the server. Check your connection and try again."
            : "Payment setup failed. Please try again."
        );
      } finally {
        setLoading(false);
      }
    })();
  };

  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Choose your plan
        </Text>
        <Text variant="body" color="secondary">
          Free during beta. No charge on your card until we come out of beta —
          you'll get an email before anything is billed.
        </Text>

        {PLANS.map((p) => {
          const active = selected === p.key;
          return (
            <Pressable
              key={p.key}
              testID={`plan-${p.key}`}
              onPress={() => setSelected(p.key)}
              className="rounded-2xl border p-4"
              style={{
                borderColor: active ? "#2563EB" : "#E5E7EB",
                borderWidth: active ? 2 : 1,
                backgroundColor: active ? "#EFF6FF" : "#FFFFFF",
              }}
            >
              <View className="flex-row items-center justify-between">
                <View className="flex-row items-center gap-2">
                  <Text variant="body" weight="bold">
                    {p.name}
                  </Text>
                  {p.highlighted && (
                    <View className="rounded-full bg-blue-600 px-2 py-0.5">
                      <Text variant="caption" style={{ color: "#FFFFFF", fontSize: 10 }}>
                        POPULAR
                      </Text>
                    </View>
                  )}
                </View>
                <View className="flex-row items-baseline">
                  <Text variant="title" weight="bold" color="primary">
                    {p.price}
                  </Text>
                  <Text variant="caption" color="secondary">
                    {p.cadence}
                  </Text>
                </View>
              </View>
              <Text variant="caption" color="secondary">
                {p.tagline}
              </Text>
              <View className="mt-3 gap-1.5">
                {p.features.map((f) => (
                  <View key={f} className="flex-row items-center gap-2">
                    <Icon name="checkmark" size={14} color="#10B981" />
                    <Text variant="caption" color="secondary">
                      {f}
                    </Text>
                  </View>
                ))}
              </View>
            </Pressable>
          );
        })}

        {error && (
          <View className="rounded-2xl bg-red-50 p-4">
            <Text variant="caption" color="warning">
              {error}
            </Text>
          </View>
        )}

        <Button
          testID="plan-continue"
          title={
            loading
              ? "Opening secure checkout…"
              : `Continue · £0 during beta (then ${plan.price}${plan.cadence})`
          }
          onPress={startCheckout}
          disabled={loading}
        />
        <View className="flex-row items-center justify-center gap-1">
          <Icon name="info" size={14} color="#6B7280" />
          <Text variant="caption" color="secondary">
            Secure payment processed by Paddle
          </Text>
        </View>
      </View>
    </ScrollView>
  );
}
