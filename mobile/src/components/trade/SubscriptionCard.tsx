import { View } from "react-native";
import { Text } from "../ui/Text";
import { planDisplayName, type SubscriptionRead } from "../../api/billing";
import { parseServerDate } from "../../lib/datetime";
import { useFeatureFlags } from "../../api/featureFlags";

const STATUS_LABELS: Record<string, string> = {
  incomplete: "Setup incomplete",
  trialing: "Free trial",
  trial_expired: "Trial expired",
  active: "Active",
  past_due: "Payment past due",
  paused: "Paused",
  canceled: "Cancelled",
};

/**
 * Read-only subscription status (App Store Guideline 3.1.1): plans are bought
 * and managed on the website, so the card only reports state. The website
 * mention below is plain text on purpose; it must never become a link.
 * Shared by Settings and the /(trade)/billing route.
 */
export function SubscriptionCard({ subscription }: { subscription: SubscriptionRead }) {
  const { data: featureFlags } = useFeatureFlags();
  const paddleBillingEnabled = featureFlags?.paddleBilling === true;
  // A "trialing" row past its trialEndsAt is effectively expired (the server
  // sweep flips it to trial_expired, but a stale row should never badge as an
  // active free trial).
  const trialEndMs = subscription.trialEndsAt
    ? parseServerDate(subscription.trialEndsAt)?.getTime()
    : undefined;
  const lapsed =
    subscription.status === "trial_expired" ||
    (subscription.status === "trialing" && trialEndMs != null && trialEndMs <= Date.now());
  const effectiveStatus = lapsed ? "trial_expired" : subscription.status;
  const trialLeft =
    subscription.status === "trialing" && !lapsed && subscription.trialEndsAt
      ? `Trial ends ${parseServerDate(subscription.trialEndsAt)?.toLocaleDateString("en-GB", {
          day: "numeric",
          month: "short",
        }) ?? "—"}`
      : null;
  const renewsAt =
    (subscription.status === "active" || subscription.status === "past_due") &&
    subscription.currentPeriodEnd
      ? `Renews ${parseServerDate(subscription.currentPeriodEnd)?.toLocaleDateString("en-GB", {
          day: "numeric",
          month: "short",
        }) ?? "—"}`
      : null;

  return (
    <View className="rounded-2xl bg-slate-100 p-4 gap-2">
      <View className="flex-row items-center justify-between">
        <Text variant="body" weight="semibold">
          Subscription
        </Text>
        <View className="rounded-full bg-white px-2 py-0.5">
          <Text testID="settings-subscription-status" variant="caption" weight="semibold">
            {STATUS_LABELS[effectiveStatus] ?? subscription.status}
          </Text>
        </View>
      </View>
      <Text testID="settings-subscription-plan" variant="body">
        {planDisplayName(subscription.planKey)} plan
      </Text>
      {trialLeft && (
        <Text variant="caption" color="secondary">
          {trialLeft}
        </Text>
      )}
      {renewsAt && (
        <Text variant="caption" color="secondary">
          {renewsAt}
        </Text>
      )}
      {subscription.status === "incomplete" && (
        <Text variant="caption" color="warning">
          Your subscription isn't active yet — finish setting it up on our website.
        </Text>
      )}
      <Text variant="caption" color="secondary">
        {paddleBillingEnabled
          ? "Manage your subscription at mytradeportal.co.uk"
          : "Free beta access is currently enabled for your account."}
      </Text>
    </View>
  );
}
