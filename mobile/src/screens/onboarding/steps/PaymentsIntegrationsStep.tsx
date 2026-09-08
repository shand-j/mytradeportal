import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Text } from "../../../components/ui/Text";

type PaymentsIntegrationsStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

const INTEGRATIONS = [
  { key: "stripe", label: "Stripe" },
  { key: "gocardless", label: "GoCardless" },
  { key: "xero", label: "Xero" },
  { key: "quickbooks", label: "QuickBooks" },
  { key: "freeagent", label: "FreeAgent" },
  { key: "google_calendar", label: "Google Calendar" },
  { key: "outlook", label: "Outlook" },
  { key: "whatsapp_business", label: "WhatsApp Business" },
];

export function PaymentsIntegrationsStep({ onNext }: PaymentsIntegrationsStepProps) {
  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Payments & integrations
        </Text>
        <Text variant="body" color="secondary">
          Connect the tools you already use. You can do this later from Settings.
        </Text>

        <View className="gap-2">
          {INTEGRATIONS.map((integration) => (
            <View
              key={integration.key}
              className="flex-row items-center justify-between rounded-xl border border-slate-200 bg-white p-4"
            >
              <Text variant="body" weight="semibold">
                {integration.label}
              </Text>
              <Text variant="caption" color="secondary">
                Not connected
              </Text>
            </View>
          ))}
        </View>

        <Button title="Skip for now" variant="outline" onPress={() => onNext({ skipped: true })} />
      </View>
    </ScrollView>
  );
}
