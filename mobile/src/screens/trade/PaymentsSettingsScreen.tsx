import { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { StripeConnectCard } from "../../components/trade/StripeConnectCard";
import { usePaymentsStatus, useUpdatePaymentsSettings } from "../../api/payments";
import { NetworkError } from "../../lib/apiClient";

export type PaymentsSettingsScreenProps = {
  onClose: () => void;
};

export function PaymentsSettingsScreen({ onClose }: PaymentsSettingsScreenProps) {
  const statusQuery = usePaymentsStatus();
  const settingsMutation = useUpdatePaymentsSettings();
  const [error, setError] = useState<string | null>(null);

  const status = statusQuery.data;
  // The default toggle is the primary control for card payments and must only
  // be toggleable when Stripe is connected AND able to take card payments —
  // a connected-but-restricted account still can't accept charges.
  const cardsLive = Boolean(status?.connected && status.chargesEnabled);

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

        <StripeConnectCard />

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
