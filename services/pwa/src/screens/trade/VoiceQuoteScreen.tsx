import { useState } from "react";
import { ScrollView, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { VoiceCaptureSheet } from "../../components/VoiceCaptureSheet";
import { MOCK_QUOTES } from "../../data/mockQuotes";
import { useOfflineStore } from "../../stores/offlineStore";
import { Quote, QuoteLineItem } from "../../types";

const DICTATION =
  "Consumer unit upgrade at a three-bed semi in Stockport. Old rewireable fuse box, no RCD protection. " +
  "Replace with a twelve-way RCBO board. Add two double sockets in the kitchen and one outdoor weatherproof socket. " +
  "Test all circuits and issue an EICR.";

// Deterministic mock of the structured extraction an LLM would return from the
// transcript above (Zod-typed line items in the real build).
const EXTRACTED: QuoteLineItem[] = [
  { id: "v1", kind: "labour", description: "Consumer unit replacement — 12-way RCBO (labour)", qty: "1", unit: "job", unitPrice: "520.00" },
  { id: "v2", kind: "materials", description: "Metal 12-way RCBO board + enclosure", qty: "1", unit: "job", unitPrice: "180.00" },
  { id: "v3", kind: "labour", description: "Install double socket (kitchen)", qty: "2", unit: "point", unitPrice: "90.00" },
  { id: "v4", kind: "labour", description: "Outdoor weatherproof socket", qty: "1", unit: "point", unitPrice: "120.00" },
  { id: "v5", kind: "labour", description: "EICR test & certificate", qty: "1", unit: "job", unitPrice: "90.00" },
  { id: "v6", kind: "callout", description: "Call-out fee", qty: "1", unit: "item", unitPrice: "45.00" },
];

type Phase = "capture" | "review";

export type VoiceQuoteScreenProps = {
  onClose: () => void;
  onCreated: (quoteId: string) => void;
};

export function VoiceQuoteScreen({ onClose, onCreated }: VoiceQuoteScreenProps) {
  const [phase, setPhase] = useState<Phase>("capture");
  const enqueue = useOfflineStore((s) => s.enqueue);
  const isOnline = useOfflineStore((s) => s.isOnline);

  const subtotal = EXTRACTED.reduce(
    (sum, i) => sum + parseFloat(i.qty) * parseFloat(i.unitPrice),
    0
  );
  const total = subtotal * 1.2;

  if (phase === "capture") {
    return (
      <VoiceCaptureSheet
        title="Dictate a quote"
        prompt="Describe the job out loud — the AI drafts the line items."
        transcript={DICTATION}
        confirmLabel="line items"
        onCancel={onClose}
        onComplete={() => setPhase("review")}
      />
    );
  }

  const createQuote = () => {
    const id = `qv-${Date.now()}`;
    const quote: Quote = {
      id,
      leadId: "",
      customerName: "New customer",
      title: "Consumer unit upgrade + extras",
      postcode: "SK8 3NJ",
      status: "draft",
      lineItems: EXTRACTED,
      assumptions: [
        "Assumed stud/plasterboard walls",
        "Assumed consumer unit is accessible",
        "Extracted from a voice note",
      ],
      aiConfidence: 82,
      vatRate: 0.2,
    };
    MOCK_QUOTES.unshift(quote);
    enqueue("quote", "Voice quote — Consumer unit upgrade");
    onCreated(id);
  };

  return (
    <Screen>
      <Header title="AI-drafted quote" onBack={onClose} />
      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 32 }}>
        <View className="flex-row items-center gap-2 rounded-2xl border border-indigo-100 bg-indigo-50 p-3">
          <Icon name="sparkles" size={18} color="#4F46E5" />
          <Text variant="caption" color="secondary" style={{ flex: 1 }}>
            AI extracted {EXTRACTED.length} line items from your voice note · confidence 82%
          </Text>
        </View>

        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          {EXTRACTED.map((item) => (
            <View key={item.id} className="flex-row items-center justify-between gap-2">
              <View style={{ flex: 1 }}>
                <Text variant="body" numberOfLines={2}>
                  {item.description}
                </Text>
                <Text variant="caption" color="secondary">
                  {item.qty} × £{parseFloat(item.unitPrice).toFixed(2)} · {item.unit}
                </Text>
              </View>
              <Text variant="body" weight="semibold">
                £{(parseFloat(item.qty) * parseFloat(item.unitPrice)).toFixed(2)}
              </Text>
            </View>
          ))}
          <View className="my-1 h-px bg-slate-200" />
          <View className="flex-row justify-between">
            <Text variant="body" weight="bold">
              Total (inc. VAT)
            </Text>
            <Text variant="title" weight="bold" color="primary">
              £{total.toFixed(2)}
            </Text>
          </View>
        </View>

        {!isOnline && (
          <View className="flex-row items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-3">
            <Icon name="cloud-offline" size={18} color="#B45309" />
            <Text variant="caption" color="secondary" style={{ flex: 1 }}>
              You're offline — this quote will be saved on your device and synced automatically.
            </Text>
          </View>
        )}
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
        <Button testID="voice-create-quote" title="Create quote & review" onPress={createQuote} />
        <Button title="Re-record" variant="outline" onPress={() => setPhase("capture")} />
      </View>
    </Screen>
  );
}
