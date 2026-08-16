import { useState } from "react";
import { ActivityIndicator, Linking, Pressable, ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";

type PlanPaymentStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

// In the offline demo we simulate the Paddle browser round-trip in-app so the
// flow stays self-contained and recordable. In production, set DEMO_MODE=false
// and the "Continue to secure payment" button opens the Paddle checkout in the
// browser; Paddle then deep-links back (mtp://onboarding/complete) to the
// dashboard on success.
const DEMO_MODE = true;
const PADDLE_CHECKOUT_URL = "https://checkout.paddle.com/checkout/custom/mtp";

type Plan = {
  key: string;
  name: string;
  price: string;
  cadence: string;
  tagline: string;
  features: string[];
  highlighted?: boolean;
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

type Phase = "select" | "checkout" | "success";

export function PlanPaymentStep({ onNext }: PlanPaymentStepProps) {
  const [selected, setSelected] = useState<string>("pro");
  const [phase, setPhase] = useState<Phase>("select");

  const plan = PLANS.find((p) => p.key === selected) ?? PLANS[1];

  const startCheckout = () => {
    if (!DEMO_MODE) {
      // Production: hand off to Paddle in the browser; Paddle deep-links back.
      Linking.openURL(`${PADDLE_CHECKOUT_URL}?plan=${plan.key}`).catch(() => {});
      return;
    }
    // Demo: simulate the secure checkout hand-off in-app.
    setPhase("checkout");
    setTimeout(() => setPhase("success"), 2400);
  };

  if (phase === "checkout") {
    return (
      <View className="gap-4">
        <View className="flex-row items-center gap-2">
          <Icon name="checkmark" size={20} color="#10B981" />
          <Text variant="title" weight="bold">
            Secure checkout
          </Text>
        </View>
        <View className="items-center gap-4 rounded-2xl border border-slate-200 bg-white p-6">
          <View className="flex-row items-center gap-2">
            <ActivityIndicator color="#2563EB" />
            <Text variant="body" weight="semibold">
              Opening Paddle secure checkout…
            </Text>
          </View>
          <Text variant="body" color="secondary" align="center">
            Complete your payment for the {plan.name} plan ({plan.price}
            {plan.cadence}) in the secure window. We'll bring you back to your dashboard when it's
            done.
          </Text>
          <View className="flex-row items-center gap-2 rounded-xl bg-slate-50 px-3 py-2">
            <Icon name="info" size={16} color="#6B7280" />
            <Text variant="caption" color="secondary">
              Payments are processed securely by Paddle.
            </Text>
          </View>
        </View>
      </View>
    );
  }

  if (phase === "success") {
    return (
      <View className="gap-4">
        <View className="items-center gap-4 rounded-2xl border border-green-200 bg-green-50 p-6">
          <View className="h-14 w-14 items-center justify-center rounded-full bg-green-500">
            <Icon name="checkmark" size={30} color="#FFFFFF" />
          </View>
          <Text variant="title" weight="bold" align="center">
            Payment successful
          </Text>
          <Text variant="body" color="secondary" align="center">
            You're on the {plan.name} plan. Your white-label customer experience is now live.
          </Text>
        </View>
        <Button
          testID="payment-go-dashboard"
          title="Go to my dashboard"
          onPress={() => onNext({ plan: plan.key })}
        />
      </View>
    );
  }

  return (
    <ScrollView className="flex-1">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Choose your plan
        </Text>
        <Text variant="body" color="secondary">
          Pick a plan to go live. You can change or cancel any time.
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

        <Button
          testID="plan-continue"
          title={`Continue to secure payment · ${plan.price}${plan.cadence}`}
          onPress={startCheckout}
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
