import { useState } from "react";
import { Linking, Pressable, ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";
import {
  CHECKOUT_PLAN_KEY,
  createBillingCheckout,
  useBillingPlans,
  type BillingPlan,
  type BillingPlanKey,
} from "../../../api/billing";
import { config } from "../../../lib/config";
import { NetworkError } from "../../../lib/apiClient";

type Plan = {
  key: BillingPlanKey;
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

// Static copy of the confirmed tier catalog — mirrors GET /billing/plans.
// Used verbatim when the endpoint is unreachable (onboarding must never be
// blocked on this fetch) and as the source of taglines/feature copy when it
// succeeds (the endpoint carries numbers, not marketing copy).
const FALLBACK_PLANS: BillingPlan[] = [
  {
    key: "sole_trader",
    name: "Sole Trader",
    monthlyPriceEnv: "PADDLE_PRICE_ID_SOLE_TRADER_MONTH",
    annualPriceEnv: "PADDLE_PRICE_ID_SOLE_TRADER_YEAR",
    monthlyPriceGbp: 25,
    annualPriceGbp: 250,
    aiAllowanceMonthly: 30,
    overageBehavior: "block",
    overagePricePence: 6,
    minSeats: 1,
    pooledAllowance: false,
    featured: false,
    trialDays: 14,
    trialExtensionDays: 30,
    trialExtensionSentAiQuotes: 3,
  },
  {
    key: "pro",
    name: "Pro",
    monthlyPriceEnv: "PADDLE_PRICE_ID_PRO_MONTH",
    annualPriceEnv: "PADDLE_PRICE_ID_PRO_YEAR",
    monthlyPriceGbp: 39,
    annualPriceGbp: 390,
    aiAllowanceMonthly: 100,
    overageBehavior: "metered",
    overagePricePence: 6,
    minSeats: 1,
    pooledAllowance: false,
    featured: true,
    trialDays: 14,
    trialExtensionDays: 30,
    trialExtensionSentAiQuotes: 3,
  },
  {
    key: "team",
    name: "Team",
    monthlyPriceEnv: "PADDLE_PRICE_ID_TEAM_MONTH",
    annualPriceEnv: "PADDLE_PRICE_ID_TEAM_YEAR",
    monthlyPriceGbp: 69,
    annualPriceGbp: 690,
    aiAllowanceMonthly: 100,
    overageBehavior: "metered",
    overagePricePence: 6,
    minSeats: 1,
    pooledAllowance: true,
    featured: false,
    trialDays: 14,
    trialExtensionDays: 30,
    trialExtensionSentAiQuotes: 3,
  },
];

const TAGLINES: Record<BillingPlanKey, string> = {
  sole_trader: "For sole traders getting started",
  pro: "For growing electrical businesses",
  team: "For multi-engineer teams",
};

function toDisplayPlan(plan: BillingPlan): Plan {
  // Flat pricing: per business, unlimited users, AI included on every plan.
  const aiLine = "AI included on every plan — no credits, no counting";
  const featuresByKey: Record<BillingPlanKey, string[]> = {
    sole_trader: ["Unlimited users", aiLine, "Unlimited quote requests", "Calendar & jobs"],
    pro: [
      "Everything in Sole Trader",
      "Invoicing & payments",
      "Team assignment",
      "Branded customer portal",
    ],
    team: ["Everything in Pro", "Priority support", "Accounting sync"],
  };
  return {
    key: plan.key,
    name: plan.name,
    price: `£${plan.monthlyPriceGbp}`,
    cadence: "/business/mo",
    tagline: TAGLINES[plan.key],
    features: featuresByKey[plan.key],
    highlighted: plan.featured,
  };
}

export function PlanPaymentStep({ data, onNext }: PlanPaymentStepProps) {
  const initial = (data?.plan as BillingPlanKey | undefined) ?? "pro";
  const [selected, setSelected] = useState<BillingPlanKey>(initial);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const plansQuery = useBillingPlans();
  const catalog = plansQuery.data ?? FALLBACK_PLANS;
  const plans = catalog.map(toDisplayPlan);

  const plan = plans.find((p) => p.key === selected) ?? plans[1];
  const trialDays = catalog[0]?.trialDays ?? 14;

  const startCheckout = () => {
    setError(null);
    setLoading(true);
    void (async () => {
      try {
        // Paddle Billing has no fully hosted checkout: the transaction's
        // checkout.url is <our page>?_ptxn=<txn>, and that page must run
        // Paddle.js. The API serves one at /billing/checkout-page.
        const checkoutPageUrl = `${config.apiBaseUrl}/billing/checkout-page`;
        // The checkout endpoint still speaks the legacy plan keys until the
        // Paddle catalog work lands, so map the new tier key back here.
        const { checkoutUrl } = await createBillingCheckout(
          CHECKOUT_PLAN_KEY[plan.key],
          checkoutPageUrl
        );
        onNext({ plan: plan.key, checkoutStarted: true });
        // Kick the user out to the checkout page; Paddle.js renders the
        // overlay there and shows a return-to-app message on completion.
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
          {trialDays}-day free trial — full features, no card needed. Send 3 AI quotes during
          your trial and we'll extend it to 30 days.
        </Text>

        {plans.map((p) => {
          const active = selected === p.key;
          return (
            <Pressable
              key={p.key}
              testID={`plan-${p.key}`}
              onPress={() => setSelected(p.key)}
              className="rounded-2xl border p-4"
              style={{
                borderColor: active ? "#0F1E26" : "#E5E7EB",
                borderWidth: active ? 2 : 1,
                backgroundColor: active ? "#F2F5F6" : "#FFFFFF",
              }}
            >
              <View className="flex-row items-center justify-between">
                <View className="flex-row items-center gap-2">
                  <Text variant="body" weight="bold">
                    {p.name}
                  </Text>
                  {p.highlighted && (
                    <View className="rounded-full bg-accent-500 px-2 py-0.5">
                      <Text variant="caption" style={{ color: "#0F1E26", fontSize: 10 }}>
                        MOST POPULAR
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
              : `Continue — ${trialDays} days free, then ${plan.price}${plan.cadence}`
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
