import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { Contact, findOrCreateContact } from "../../api/contacts";
import { createQuoteRequest } from "../../api/quoteRequests";
import { generateQuoteAsync } from "../../api/quotes";
import { useQuoteGenerationStore } from "../../stores/quoteGenerationStore";
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

/** Job-details length at which the AI has enough to quote from. */
const MIN_JOB_DETAILS_CHARS = 30;

export type ManualLeadScreenProps = {
  onClose: () => void;
  /** Pre-fill the customer name (e.g. text already typed in the quote intake). */
  prefillName?: string;
  /** Override the post-save navigation (e.g. return to the quote intake). */
  onSaved?: (contact: Contact) => void;
};

export function ManualLeadScreen({ onClose, prefillName, onSaved }: ManualLeadScreenProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const startGeneration = useQuoteGenerationStore((s) => s.start);
  const [name, setName] = useState(prefillName ?? "");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [postcode, setPostcode] = useState("");
  const [jobDetails, setJobDetails] = useState("");
  const [source, setSource] = useState<LeadSource>("manual");
  const [urgency, setUrgency] = useState<string>("this_week");
  const [submitting, setSubmitting] = useState<"save" | "quote" | null>(null);
  const [error, setError] = useState<string | null>(null);

  // "Save customer" needs a name plus one way to reach them (phone or email).
  const canSaveCustomer =
    name.trim().length > 0 && (phone.trim().length > 0 || email.trim().length > 0);
  // "Generate AI quote" appears once the job details are long enough to quote from.
  const hasJobDetails = jobDetails.trim().length >= MIN_JOB_DETAILS_CHARS;

  const saveCustomer = async (): Promise<Contact> => {
    const contact = await findOrCreateContact({
      name: name.trim(),
      phone: phone.trim() || null,
      email: email.trim() || null,
      address: address.trim() || null,
      postcode: postcode.trim().toUpperCase() || null,
      notes: jobDetails.trim() || null,
    });
    await queryClient.invalidateQueries({ queryKey: ["contacts"] });
    return contact;
  };

  const handleSaveCustomer = async () => {
    setError(null);
    setSubmitting("save");
    try {
      const contact = await saveCustomer();
      if (onSaved) {
        onSaved(contact);
        return;
      }
      router.replace(`/(trade)/customer/${contact.id}`);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Couldn't save the customer. Please try again."
      );
      setSubmitting(null);
    }
  };

  const handleGenerateQuote = async () => {
    setError(null);
    setSubmitting("quote");
    try {
      const contact = await saveCustomer();
      const lead = await createQuoteRequest({
        contactId: contact.id,
        source: "manual",
        rawText: jobDetails.trim(),
        structuredData: { receivedVia: source },
        urgency,
      });
      await queryClient.invalidateQueries({ queryKey: ["quote-requests"] });
      // Same pattern as quote intake: 202 kick-off, then the quotes list shows
      // the generating banner until the quote_ready notification lands.
      await generateQuoteAsync({
        quoteRequestId: lead.id,
        description: jobDetails.trim(),
      });
      startGeneration();
      router.replace("/(trade)/quotes");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : "Couldn't start the AI quote. Please try again."
      );
      setSubmitting(null);
    }
  };

  return (
    <Screen>
      <Header title="Add New Customer" onBack={() => onClose()} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          className="flex-1"
          contentContainerClassName="gap-3 pb-4"
          keyboardShouldPersistTaps="handled"
        >
          <Text variant="body" color="secondary">
            Capture the customer's details first — then save them, or generate an AI quote from
            the job details.
          </Text>

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
              placeholder="Email"
              keyboardType="email-address"
              autoCapitalize="none"
            />
            <TextInput
              className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
              value={address}
              onChangeText={setAddress}
              placeholder="Address"
            />
            <TextInput
              className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
              value={postcode}
              onChangeText={setPostcode}
              placeholder="Postcode"
              autoCapitalize="characters"
            />
            <Text variant="caption" color="secondary">
              A name plus a phone number or email is enough to save. Add an email so they can
              track their quote in the customer app.
            </Text>
          </View>

          <View className="rounded-2xl bg-slate-100 p-4 gap-2">
            <Text variant="body" weight="semibold">
              Job details (optional)
            </Text>
            <TextInput
              className="h-32 rounded-xl border border-slate-200 bg-white px-4 pt-3 text-base text-slate-900"
              value={jobDetails}
              onChangeText={setJobDetails}
              placeholder="Describe the job — or paste the customer's message, email, or voice note transcript..."
              multiline
              textAlignVertical="top"
            />
            <Text variant="caption" color="secondary">
              {hasJobDetails
                ? "Enough detail to generate an AI quote."
                : `Write at least ${MIN_JOB_DETAILS_CHARS} characters and you can generate an AI quote straight away.`}
            </Text>
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

          {error && (
            <View className="rounded-2xl bg-amber-50 p-3">
              <Text testID="manual-lead-error" variant="caption" color="warning">
                {error}
              </Text>
            </View>
          )}
        </ScrollView>

        <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
          {hasJobDetails && (
            <Button
              testID="manual-lead-generate-quote"
              title={submitting === "quote" ? "Starting…" : "Generate AI quote"}
              onPress={() => void handleGenerateQuote()}
              disabled={!canSaveCustomer || submitting !== null}
            />
          )}
          <Button
            testID="manual-lead-submit"
            title={submitting === "save" ? "Saving…" : "Save customer"}
            variant={hasJobDetails ? "outline" : "primary"}
            onPress={() => void handleSaveCustomer()}
            disabled={!canSaveCustomer || submitting !== null}
          />
          <Button title="Cancel" variant="outline" onPress={() => onClose()} />
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
