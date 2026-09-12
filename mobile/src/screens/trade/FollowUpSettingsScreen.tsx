import { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";

export type FollowUpSettingsScreenProps = {
  onClose: () => void;
};

export function FollowUpSettingsScreen({ onClose }: FollowUpSettingsScreenProps) {
  const [quoteReminderEnabled, setQuoteReminderEnabled] = useState(true);
  const [invoiceReminderEnabled, setInvoiceReminderEnabled] = useState(true);
  const [quoteDelay, setQuoteDelay] = useState("3");
  const [invoiceDelay, setInvoiceDelay] = useState("7");

  return (
    <Screen>
      <Header testID="follow-up-back" title="Follow-ups" onBack={onClose} />

      <ScrollView className="flex-1" contentContainerClassName="gap-4 pb-4">
        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Automatic reminders
          </Text>
          <Text variant="caption" color="secondary">
            Choose when the app nudges customers who have not responded.
          </Text>

          <Toggle label="Quote reminders" value={quoteReminderEnabled} onChange={setQuoteReminderEnabled} />
          <Toggle label="Invoice reminders" value={invoiceReminderEnabled} onChange={setInvoiceReminderEnabled} />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Channel
          </Text>
          <Text variant="caption" color="secondary">
            Reminders are sent by email.
          </Text>
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-4">
          <Text variant="body" weight="semibold">
            Delay settings
          </Text>
          <Text variant="caption" color="secondary">
            Days to wait before the first follow-up.
          </Text>

          <FormField
            label="Quote reminder delay (days)"
            value={quoteDelay}
            onChangeText={setQuoteDelay}
            placeholder="3"
            keyboardType="number-pad"
            helper="Days after sending the quote before the first reminder."
          />

          <FormField
            label="Invoice reminder delay (days)"
            value={invoiceDelay}
            onChangeText={setInvoiceDelay}
            placeholder="7"
            keyboardType="number-pad"
            helper="Days after the due date before the first reminder."
          />
        </View>
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
        <Button title="Save settings" onPress={onClose} />
      </View>
    </Screen>
  );
}

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <Pressable onPress={() => onChange(!value)}>
      <View className="flex-row items-center justify-between py-1">
        <Text variant="body">{label}</Text>
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
