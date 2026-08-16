import { useState } from "react";
import { ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { MOCK_LEADS } from "../../data/mockLeads";
import { Lead, LeadSource, LeadStatus } from "../../types";

const SOURCES: { key: LeadSource; label: string }[] = [
  { key: "whatsapp", label: "WhatsApp" },
  { key: "sms", label: "SMS" },
  { key: "phone", label: "Phone" },
  { key: "manual", label: "Manual" },
];

const URGENCIES: { key: LeadStatus | "today" | "this_week" | "this_month" | "flexible"; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "this_week", label: "This week" },
  { key: "this_month", label: "This month" },
  { key: "flexible", label: "Flexible" },
];

export type ManualLeadScreenProps = {
  onClose: (lead?: Lead) => void;
};

export function ManualLeadScreen({ onClose }: ManualLeadScreenProps) {
  const [customerMessage, setCustomerMessage] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [postcode, setPostcode] = useState("");
  const [source, setSource] = useState<LeadSource>("manual");
  const [urgency, setUrgency] = useState<string>("this_week");
  const [generating, setGenerating] = useState(false);

  const generate = () => {
    setGenerating(true);
    setTimeout(() => {
      const newLead: Lead = {
        id: `lead-${Date.now()}`,
        title: "New electrical work",
        postcode: postcode || "SK8 3NJ",
        urgency,
        source,
        customerName: name || "New customer",
        customerPhone: phone,
        estimate: "£TBC",
        badge: "Draft",
        status: "draft",
        note: customerMessage,
        createdAt: new Date().toISOString(),
      };
      MOCK_LEADS.unshift(newLead);
      setGenerating(false);
      onClose(newLead);
    }, 1500);
  };

  const canGenerate = customerMessage.trim().length > 10 && name.trim() && postcode.trim();

  return (
    <Screen>
      <Header title="AI lead entry" onBack={() => onClose()} />

      <ScrollView className="flex-1" contentContainerClassName="gap-3 pb-4">
        <Text variant="body" color="secondary">
          Paste a customer message, email, or voice note transcript. The AI will draft a lead and
          quote.
        </Text>

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Customer message
          </Text>
          <TextInput
            className="h-32 rounded-xl border border-slate-200 bg-white px-4 pt-3 text-base text-slate-900"
            value={customerMessage}
            onChangeText={setCustomerMessage}
            placeholder="Paste WhatsApp, SMS, email or voice transcript..."
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
            className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
            value={postcode}
            onChangeText={setPostcode}
            placeholder="Postcode"
            autoCapitalize="characters"
          />
        </View>

        {generating && (
          <View className="rounded-2xl bg-slate-100 p-4">
            <Text variant="body" color="secondary" align="center">
              Analysing message and drafting quote…
            </Text>
          </View>
        )}
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
        <Button title="Draft lead & quote with AI" onPress={generate} disabled={!canGenerate || generating} />
        <Button title="Skip AI, save manually" variant="outline" onPress={() => onClose()} />
      </View>
    </Screen>
  );
}
