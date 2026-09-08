import { useState } from "react";
import { ScrollView, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { findOrCreateContact } from "../../api/contacts";
import { createQuoteRequest } from "../../api/quoteRequests";
import { ApiError } from "../../lib/apiClient";
import { LeadSource } from "../../types";

const SOURCES: { key: LeadSource; label: string }[] = [
  { key: "phone", label: "Phone" },
  { key: "manual", label: "Manual" },
];

const URGENCIES: { key: string; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "this_week", label: "This week" },
  { key: "this_month", label: "This month" },
  { key: "flexible", label: "Flexible" },
];

export type ManualLeadScreenProps = {
  onClose: () => void;
};

export function ManualLeadScreen({ onClose }: ManualLeadScreenProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [customerMessage, setCustomerMessage] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [postcode, setPostcode] = useState("");
  const [source, setSource] = useState<LeadSource>("manual");
  const [urgency, setUrgency] = useState<string>("this_week");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const contact = await findOrCreateContact({
        name: name.trim(),
        phone: phone.trim() || null,
        email: email.trim() || null,
        postcode: postcode.trim().toUpperCase() || null,
        notes: customerMessage.trim() || null,
      });
      const created = await createQuoteRequest({
        contactId: contact.id,
        source: "manual",
        rawText: customerMessage.trim(),
        structuredData: { receivedVia: source },
        urgency,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["quote-requests"] }),
        queryClient.invalidateQueries({ queryKey: ["contacts"] }),
      ]);
      setSubmitted(true);
      // Brief acknowledgement, then open the new lead.
      setTimeout(() => {
        router.replace(`/(trade)/lead/${created.id}`);
      }, 800);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : "Couldn't save the lead. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const canGenerate = customerMessage.trim().length > 10 && name.trim() && postcode.trim();

  return (
    <Screen>
      <Header title="Manual lead entry" onBack={() => onClose()} />

      <ScrollView className="flex-1" contentContainerClassName="gap-3 pb-4">
        <Text variant="body" color="secondary">
          Paste a customer message, email, or voice note transcript to pre-fill a lead.
        </Text>

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Customer message
          </Text>
          <TextInput
            className="h-32 rounded-xl border border-slate-200 bg-white px-4 pt-3 text-base text-slate-900"
            value={customerMessage}
            onChangeText={setCustomerMessage}
            placeholder="Paste an email or message transcript..."
            multiline
            textAlignVertical="top"
          />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Source
          </Text>
          <View className="flex-row flex-wrap gap-2">
            {SOURCES.map((s) => (
              <Button
                key={s.key}
                title={s.label}
                variant={source === s.key ? "primary" : "outline"}
                onPress={() => setSource(s.key)}
              />
            ))}
          </View>
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Urgency
          </Text>
          <View className="flex-row flex-wrap gap-2">
            {URGENCIES.map((u) => (
              <Button
                key={u.key}
                title={u.label}
                variant={urgency === u.key ? "primary" : "outline"}
                onPress={() => setUrgency(u.key)}
              />
            ))}
          </View>
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Customer details
          </Text>
          <TextInput
            className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
            value={name}
            onChangeText={setName}
            placeholder="Name"
          />
          <TextInput
            className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
            value={phone}
            onChangeText={setPhone}
            placeholder="Phone"
            keyboardType="phone-pad"
          />
          <TextInput
            testID="manual-lead-email"
            className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
            value={email}
            onChangeText={setEmail}
            placeholder="Email (optional)"
            keyboardType="email-address"
            autoCapitalize="none"
          />
          <Text variant="caption" color="secondary">
            Add an email so they can track their quote in the customer app.
          </Text>
          <TextInput
            className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
            value={postcode}
            onChangeText={setPostcode}
            placeholder="Postcode"
            autoCapitalize="characters"
          />
        </View>

        {error && (
          <View className="rounded-2xl bg-amber-50 p-3">
            <Text testID="manual-lead-error" variant="caption" color="warning">
              {error}
            </Text>
          </View>
        )}

        {submitted && (
          <View className="rounded-2xl bg-slate-100 p-4">
            <Text variant="body" color="secondary" align="center">
              Lead saved — opening it now…
            </Text>
          </View>
        )}
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
        <Button
          testID="manual-lead-submit"
          title={submitting ? "Saving…" : "Create lead"}
          onPress={() => void generate()}
          disabled={!canGenerate || submitting || submitted}
        />
        <Button title="Cancel" variant="outline" onPress={() => onClose()} />
      </View>
    </Screen>
  );
}
