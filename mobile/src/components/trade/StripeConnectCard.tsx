import { View } from "react-native";
import { Button } from "../ui/Button";
import { Text } from "../ui/Text";
import { usePaymentsStatus, type PaymentsStatus } from "../../api/payments";
import { useStripeConnectOnboarding } from "../../hooks/useStripeConnectOnboarding";

function statusLabel(status: PaymentsStatus): string {
  if (!status.connected) return "Not connected";
  if (status.chargesEnabled && status.payoutsEnabled) return "Connected — accepting cards";
  return "Connected — restricted";
}

function statusDetail(status: PaymentsStatus): string {
  if (!status.connected) {
    return "Connect Stripe to take card payments on your invoices.";
  }
  if (status.chargesEnabled && status.payoutsEnabled) {
    return "Your customers can pay invoices online by card.";
  }
  return "Stripe still needs a few details before payouts are enabled — finish setup to lift the restriction.";
}

/**
 * Stripe connection status + connect button, shared by app onboarding (the
 * card-payments gate) and Settings → Payments so both surfaces show the same
 * in-app onboarding view. Connecting opens Stripe in the in-app browser (see
 * useStripeConnectOnboarding); status re-syncs automatically on return.
 */
export function StripeConnectCard() {
  const statusQuery = usePaymentsStatus();
  const { start, connecting, error } = useStripeConnectOnboarding();
  const status = statusQuery.data;

  return (
    <View className="gap-4">
      <View className="rounded-2xl bg-slate-100 p-4 gap-2">
        <View className="flex-row items-center justify-between">
          <Text variant="body" weight="semibold">
            Stripe connection
          </Text>
          <View className="rounded-full bg-white px-2 py-0.5">
            <Text testID="payments-status" variant="caption" weight="semibold">
              {statusQuery.isLoading ? "Loading…" : status ? statusLabel(status) : "Unavailable"}
            </Text>
          </View>
        </View>
        {status && (
          <Text variant="caption" color="secondary">
            {statusDetail(status)}
          </Text>
        )}
        <Text variant="caption" color="secondary">
          Stripe pays out to your bank on a rolling schedule — usually 2 business days.
        </Text>
        {status && !status.stripeConfigured && (
          <Text variant="caption" color="secondary">
            Card payments aren't switched on yet — check back soon.
          </Text>
        )}
        {(!status || (status.stripeConfigured && !status.onboardingComplete)) && (
          <Button
            testID="payments-connect"
            title={
              connecting
                ? "Opening Stripe…"
                : status?.connected
                  ? "Finish Stripe setup"
                  : "Connect Stripe"
            }
            disabled={connecting || statusQuery.isLoading}
            onPress={() => void start()}
          />
        )}
        {status?.connected && (
          <Button
            testID="payments-refresh-status"
            title={statusQuery.isFetching ? "Refreshing…" : "Refresh status"}
            variant="outline"
            disabled={statusQuery.isFetching}
            onPress={() => void statusQuery.refetch()}
          />
        )}
      </View>

      {error && (
        <View className="rounded-2xl bg-amber-50 p-3">
          <Text testID="payments-error" variant="caption" color="warning">
            {error}
          </Text>
        </View>
      )}
    </View>
  );
}
