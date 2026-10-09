import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";
import { useBillingPlans, type BillingPlan, type BillingPlanKey } from "../../../api/billing";

type Plan = {
  key: BillingPlanKey;
  name: string;
  price: string;
  annualPrice: string;
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
export const FALLBACK_PLANS: BillingPlan[] = [
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
    seats: 1,
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
    seats: 5,
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
    seats: 15,
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
  // Flat pricing per business, seat-capped tiers (1 / 5 / 15 users), AI
  // included on every plan.
  const aiLine = "AI included on every plan — no credits, no counting";
  const seatLine = plan.seats === 1 ? "1 user" : `Up to ${plan.seats} users`;
  const featuresByKey: Record<BillingPlanKey, string[]> = {
    sole_trader: [seatLine, aiLine, "Unlimited quote requests", "Calendar & jobs"],
    pro: [
      "Everything in Sole Trader",
      seatLine,
      "Invoicing & payments",
      "Team assignment",
      "Branded customer portal",
    ],
    team: ["Everything in Pro", seatLine, "Priority support"],
  };
  return {
    key: plan.key,
    name: plan.name,
    price: `£${plan.monthlyPriceGbp}`,
    annualPrice: `£${plan.annualPriceGbp}/year`,
    cadence: "/business/mo",
    tagline: TAGLINES[plan.key],
    features: featuresByKey[plan.key],
    highlighted: plan.featured,
  };
}

/**
 * Read-only plan step (App Store Guideline 3.1.1): the app shows the plans
 * and prices but carries no purchase flow — subscriptions are sold on the
 * website. The website mention below is plain text on purpose; it must never
 * become a link.
 */
export function PlanPaymentStep({ onNext }: PlanPaymentStepProps) {
  const plansQuery = useBillingPlans();
  const catalog = plansQuery.data ?? FALLBACK_PLANS;
  const plans = catalog.map(toDisplayPlan);
  const trialDays = catalog[0]?.trialDays ?? 14;

  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Choose your plan
        </Text>
        <Text variant="body" color="secondary">
          Every plan starts with a {trialDays}-day free trial — full features, no card needed until
          the trial ends. Subscriptions are set up on our website, then you sign in here.
        </Text>

        {plans.map((p) => (
          <View
            key={p.key}
            testID={`plan-${p.key}`}
            className="rounded-2xl border p-4"
            style={{
              borderColor: p.highlighted ? "#0F1E26" : "#E5E7EB",
              borderWidth: p.highlighted ? 2 : 1,
              backgroundColor: "#FFFFFF",
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
              {p.tagline} · or {p.annualPrice}
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
          </View>
        ))}

        <View className="flex-row items-center justify-center gap-1">
          <Icon name="info" size={14} color="#6B7280" />
          <Text variant="caption" color="secondary" align="center">
            Subscribe at mytradeportal.co.uk
          </Text>
        </View>

        <Button
          testID="plan-continue"
          title="I've subscribed — continue"
          onPress={() => onNext()}
        />
      </View>
    </ScrollView>
  );
}
