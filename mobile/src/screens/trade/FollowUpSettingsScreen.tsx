import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { fetchFollowUpSettings, updateFollowUpSettings } from "../../api/businesses";
import { ApiError, NetworkError } from "../../lib/apiClient";

export type FollowUpSettingsScreenProps = {
  onClose: () => void;
};

const ROUNDING_OPTIONS: { value: number; label: string }[] = [
  { value: 0, label: "Off" },
  { value: 5, label: "£5" },
  { value: 10, label: "£10" },
];

export function FollowUpSettingsScreen({ onClose }: FollowUpSettingsScreenProps) {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ["follow-up-settings"], queryFn: fetchFollowUpSettings });

  const [quoteReminderEnabled, setQuoteReminderEnabled] = useState(true);
  const [invoiceReminderEnabled, setInvoiceReminderEnabled] = useState(true);
  const [quoteMax, setQuoteMax] = useState("3");
  const [quoteInterval, setQuoteInterval] = useState("3");
  const [invoiceInterval, setInvoiceInterval] = useState("7");
  const [rounding, setRounding] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const settings = settingsQuery.data;
    if (!settings) return;
    setQuoteReminderEnabled(settings.quoteRemindersEnabled);
    setInvoiceReminderEnabled(settings.invoiceRemindersEnabled);
    setQuoteMax(String(settings.quoteReminderMax));
    setQuoteInterval(String(settings.quoteReminderIntervalDays));
    setInvoiceInterval(String(settings.invoiceReminderIntervalDays));
    setRounding(settings.quoteRounding);
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: updateFollowUpSettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["follow-up-settings"] });
      void queryClient.invalidateQueries({ queryKey: ["current-tenant"] });
      onClose();
    },
    onError: (err) => {
      if (err instanceof NetworkError) {
        setError("Can't reach the server. Check your connection and try again.");
      } else if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Couldn't save follow-up settings. Please try again.");
      }
    },
  });

  const parseDays = (raw: string, min: number, max: number): number | null => {
    const value = Number(raw.trim());
    if (!Number.isInteger(value) || value < min || value > max) return null;
    return value;
  };

  const save = () => {
    setError(null);
    const parsedQuoteMax = parseDays(quoteMax, 1, 10);
    if (parsedQuoteMax === null) {
      setError("Number of quote reminders must be between 1 and 10.");
      return;
    }
    const parsedQuoteInterval = parseDays(quoteInterval, 1, 90);
    if (parsedQuoteInterval === null) {
      setError("Quote reminder interval must be between 1 and 90 days.");
      return;
    }
    const parsedInvoiceInterval = parseDays(invoiceInterval, 1, 90);
    if (parsedInvoiceInterval === null) {
      setError("Invoice reminder interval must be between 1 and 90 days.");
      return;
    }
    saveMutation.mutate({
      quoteRemindersEnabled: quoteReminderEnabled,
      quoteReminderMax: parsedQuoteMax,
      quoteReminderIntervalDays: parsedQuoteInterval,
      invoiceRemindersEnabled: invoiceReminderEnabled,
      invoiceReminderIntervalDays: parsedInvoiceInterval,
      quoteRounding: rounding,
    });
  };

  return (
    <Screen>
      <Header testID="follow-up-back" title="Follow-ups" onBack={onClose} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          className="flex-1"
          style={{ minHeight: 0 }}
          contentContainerClassName="gap-4 pb-6"
          keyboardShouldPersistTaps="handled"
        >
          <Text variant="body" color="secondary">
            Choose when the app nudges customers who have not responded. Reminders are sent by
            email.
          </Text>

          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Quote reminders
            </Text>
            <Text variant="caption" color="secondary">
              Sent quotes the customer has not answered are chased automatically, then stop.
            </Text>
            <Toggle
              label="Send quote reminders"
              value={quoteReminderEnabled}
              onChange={setQuoteReminderEnabled}
            />
            {quoteReminderEnabled && (
              <>
                <FormField
                  testID="follow-up-quote-max"
                  label="Number of reminders"
                  value={quoteMax}
                  onChangeText={setQuoteMax}
                  placeholder="3"
                  keyboardType="number-pad"
                  maxLength={2}
                  helper="How many reminders to send before giving up (1-10)."
                />
                <FormField
                  testID="follow-up-quote-interval"
                  label="Days between reminders"
                  value={quoteInterval}
                  onChangeText={setQuoteInterval}
                  placeholder="3"
                  keyboardType="number-pad"
                  maxLength={2}
                  helper="Days after sending the quote (or the last reminder) before the next one."
                />
              </>
            )}
          </View>

          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Invoice reminders
            </Text>
            <Text variant="caption" color="secondary">
              Unpaid invoices are chased until they are paid or cancelled.
            </Text>
            <Toggle
              label="Send invoice reminders"
              value={invoiceReminderEnabled}
              onChange={setInvoiceReminderEnabled}
            />
            {invoiceReminderEnabled && (
              <FormField
                testID="follow-up-invoice-interval"
                label="Days between reminders"
                value={invoiceInterval}
                onChangeText={setInvoiceInterval}
                placeholder="7"
                keyboardType="number-pad"
                maxLength={2}
                helper="Days after the due date (or the last reminder) before the next one."
              />
            )}
          </View>

          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Quote total rounding
            </Text>
            <Text variant="caption" color="secondary">
              Round new quote totals up to the nearest £5 or £10 (e.g. £1,236.40 → £1,240). The
              rounded amount is shown on the quote.
            </Text>
            <View className="flex-row gap-2">
              {ROUNDING_OPTIONS.map((option) => {
                const selected = rounding === option.value;
                return (
                  <Pressable
                    key={option.value}
                    testID={`follow-up-rounding-${option.value}`}
                    onPress={() => setRounding(option.value)}
                  >
                    <View
                      className={`rounded-full px-4 py-2 border ${
                        selected ? "bg-primary border-primary" : "bg-white border-slate-200"
                      }`}
                    >
                      <Text variant="body" weight={selected ? "semibold" : "normal"}>
                        {option.label}
                      </Text>
                    </View>
                  </Pressable>
                );
              })}
            </View>
          </View>

          {error && (
            <View className="rounded-xl bg-amber-50 p-3">
              <Text testID="follow-up-error" variant="caption" color="warning">
                {error}
              </Text>
            </View>
          )}
        </ScrollView>

        <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
          <Button
            testID="follow-up-save"
            title={saveMutation.isPending ? "Saving…" : "Save settings"}
            disabled={saveMutation.isPending}
            onPress={save}
          />
        </View>
      </KeyboardAvoidingView>
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
