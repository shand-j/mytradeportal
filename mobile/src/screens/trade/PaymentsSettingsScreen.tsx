import { useState } from "react";
import { Linking, Pressable, ScrollView, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import {
  connectStripe,
  usePaymentsStatus,
  useUpdatePaymentsSettings,
  type PaymentsStatus,
} from "../../api/payments";
import { ApiError, NetworkError } from "../../lib/apiClient";

export type PaymentsSettingsScreenProps = {
  onClose: () => void;
};

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

export function PaymentsSettingsScreen({ onClose }: PaymentsSettingsScreenProps) {
  const statusQuery = usePaymentsStatus();
  const settingsMutation = useUpdatePaymentsSettings();
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const status = statusQuery.data;
  // The default toggle is the primary control for card payments and must only
  // be toggleable when Stripe is connected AND able to take card payments —
  // a connected-but-restricted account still can't accept charges.
  const cardsLive = Boolean(status?.connected && status.chargesEnabled);

  const openStripeOnboarding = async () => {
    setError(null);
    setConnecting(true);
    try {
      const { onboardingUrl } = await connectStripe();
      const opened = await Linking.canOpenURL(onboardingUrl);
      if (opened) {
        await Linking.openURL(onboardingUrl);
      } else {
        setError("Couldn't open Stripe setup. Try again.");
      }
    } catch (err) {
      if (err instanceof NetworkError) {
        setError("Can't reach the server. Check your connection and try again.");
      } else if (err instanceof ApiError && err.status === 503) {
        setError("Card payments aren't available yet. Please try again later.");
      } else {
        setError("Couldn't start Stripe setup. Please try again.");
      }
    } finally {
      setConnecting(false);
    }
  };

  const toggleDefault = (value: boolean) => {
    setError(null);
    settingsMutation.mutate(
      { acceptCardDefault: value },
      {
        onError: (err) => {
          setError(
            err instanceof NetworkError
              ? "Can't reach the server. Check your connection and try again."
              : "Couldn't save the setting. Please try again."
          );
        },
      }
    );
  };

  return (
    <Screen>
      <Header testID="payments-back" title="Payments" onBack={onClose} />

      <ScrollView className="flex-1" contentContainerClassName="gap-4 pb-6">
        <Text variant="body" color="secondary">
          Take card payments on your invoices with Stripe.
        </Text>

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
          {(!status || !status.onboardingComplete) && (
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
              onPress={() => void openStripeOnboarding()}
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

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            New invoices
          </Text>
          <Text variant="caption" color="secondary">
            {cardsLive
              ? "New invoices offer online card payment by default. You can override this per invoice."
              : "Connect Stripe above to let customers pay invoices online by card."}
          </Text>
          <Toggle
            testID="payments-accept-card-default"
            label="Accept card payments on new invoices"
            value={cardsLive ? (status?.acceptCardDefault ?? false) : false}
            disabled={!cardsLive || settingsMutation.isPending}
            onChange={toggleDefault}
          />
        </View>

        {error && (
          <View className="rounded-2xl bg-amber-50 p-3">
            <Text testID="payments-error" variant="caption" color="warning">
              {error}
            </Text>
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

function Toggle({
  label,
  value,
  disabled,
  onChange,
  testID,
}: {
  label: string;
  value: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
  testID?: string;
}) {
  return (
    <Pressable testID={testID} disabled={disabled} onPress={() => onChange(!value)}>
      <View className={`flex-row items-center justify-between py-1 ${disabled ? "opacity-50" : ""}`}>
        <Text variant="body" style={{ flex: 1, paddingRight: 12 }}>
          {label}
        </Text>
        <View
          className={`w-12 h-7 rounded-full px-0.5 justify-center ${value ? "bg-primary" : "bg-slate-200"}`}
        >
          <View
            className="w-6 h-6 rounded-full bg-white"
            style={{ transform: [{ translateX: value ? 20 : 0 }] }}
          />
        </View>
      </View>
    </Pressable>
  );
}
