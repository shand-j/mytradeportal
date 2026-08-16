import { useMemo, useState } from "react";
import { ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { IconButton } from "../../components/ui/IconButton";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { MOCK_LEADS } from "../../data/mockLeads";
import { MOCK_QUOTES } from "../../data/mockQuotes";
import { Lead, Quote, QuoteLineItem } from "../../types";
import { RequestInfoScreen } from "./RequestInfoScreen";

const MODEL_OPTIONS = [
  { key: "time_materials", label: "Time & materials" },
  { key: "per_point", label: "Per point" },
] as const;

function buildTimeItems(seed: Quote | undefined): QuoteLineItem[] {
  return (
    seed?.lineItems ?? [
      { id: "1", kind: "labour", description: "Consumer unit replacement labour", qty: "1", unit: "job", unitPrice: "520.00" },
      { id: "2", kind: "materials", description: "Metal 12-way RCBO board + extras", qty: "1", unit: "job", unitPrice: "180.00" },
      { id: "3", kind: "callout", description: "Call-out fee", qty: "1", unit: "item", unitPrice: "45.00" },
    ]
  );
}

function buildPointItems(seed: Quote | undefined, lead?: Lead): QuoteLineItem[] {
  if (seed?.title.toLowerCase().includes("ev charger")) {
    return [
      { id: "pp-1", kind: "labour", description: "EV charger install (per point)", qty: "1", unit: "point", unitPrice: "450.00" },
      { id: "pp-2", kind: "materials", description: "Cable and protection (per point)", qty: "1", unit: "point", unitPrice: "120.00" },
      { id: "pp-3", kind: "callout", description: "Call-out fee", qty: "1", unit: "item", unitPrice: "45.00" },
    ];
  }
  if (lead?.title.toLowerCase().includes("consumer unit") || seed?.title.toLowerCase().includes("consumer unit")) {
    return [
      { id: "pp-1", kind: "labour", description: "Consumer unit replacement (fixed price)", qty: "1", unit: "job", unitPrice: "750.00" },
      { id: "pp-2", kind: "materials", description: "RCBO protection per circuit", qty: "8", unit: "point", unitPrice: "45.00" },
      { id: "pp-3", kind: "callout", description: "Call-out fee", qty: "1", unit: "item", unitPrice: "45.00" },
    ];
  }
  return [
    { id: "pp-1", kind: "labour", description: "Install double socket", qty: "4", unit: "point", unitPrice: "100.00" },
    { id: "pp-2", kind: "materials", description: "Double socket faceplate and back box", qty: "4", unit: "point", unitPrice: "25.00" },
    { id: "pp-3", kind: "callout", description: "Call-out fee", qty: "1", unit: "item", unitPrice: "45.00" },
  ];
}

export type QuoteEditScreenProps = {
  lead?: Lead;
  seed?: Quote;
  onClose: () => void;
};

export function QuoteEditScreen({ lead, seed, onClose }: QuoteEditScreenProps) {
  const seedQuote = seed ?? (lead ? MOCK_QUOTES.find((q) => q.leadId === lead.id) : undefined);

  const resolvedLead = useMemo(
    () => lead ?? (seedQuote ? MOCK_LEADS.find((l) => l.id === seedQuote.leadId) : undefined),
    [lead, seedQuote]
  );

  const [pricingModel, setPricingModel] = useState<"time_materials" | "per_point">("time_materials");
  const [timeItems, setTimeItems] = useState<QuoteLineItem[]>(() => buildTimeItems(seedQuote));
  const [pointItems, setPointItems] = useState<QuoteLineItem[]>(() => buildPointItems(seedQuote, resolvedLead));
  const [showRequestInfo, setShowRequestInfo] = useState(false);

  const items = pricingModel === "time_materials" ? timeItems : pointItems;

  const updateItems = (fn: (prev: QuoteLineItem[]) => QuoteLineItem[]) => {
    if (pricingModel === "time_materials") {
      setTimeItems(fn);
    } else {
      setPointItems(fn);
    }
  };

  const vatRate = 0.2;

  const totals = useMemo(() => {
    const subtotal = items.reduce((sum, item) => {
      const qty = parseFloat(item.qty) || 0;
      const price = parseFloat(item.unitPrice) || 0;
      return sum + qty * price;
    }, 0);
    const vat = subtotal * vatRate;
    return { subtotal, vat, total: subtotal + vat };
  }, [items]);

  const updateItem = (id: string, field: keyof QuoteLineItem, value: string) => {
    updateItems((prev) => prev.map((item) => (item.id === id ? { ...item, [field]: value } : item)));
  };

  const addLine = () => {
    updateItems((prev) => [
      ...prev,
      { id: Date.now().toString(), kind: "labour", description: "", qty: "1", unit: "item", unitPrice: "0.00" },
    ]);
  };

  const removeItem = (id: string) => {
    updateItems((prev) => prev.filter((item) => item.id !== id));
  };

  const title = resolvedLead?.title ?? seedQuote?.title ?? "Review AI quote";
  const postcode = resolvedLead?.postcode ?? seedQuote?.postcode ?? "SK8 3NJ";
  const customerName = resolvedLead?.customerName ?? seedQuote?.customerName ?? "Customer";
  const confidence = seedQuote?.aiConfidence ?? 78;
  const isFromLead = Boolean(resolvedLead);

  if (showRequestInfo && resolvedLead) {
    return <RequestInfoScreen lead={resolvedLead} quote={seedQuote} onClose={() => setShowRequestInfo(false)} />;
  }

  return (
    <Screen>
      <Header testID="quote-edit-back" title="Review AI quote" onBack={onClose} />

      <View className="rounded-xl bg-slate-100 p-3 gap-1 mb-3">
        <Text variant="body" weight="semibold">
          {title}
        </Text>
        <Text variant="caption" color="secondary">
          {customerName} · {postcode}
        </Text>
        <View className="self-start rounded-md bg-blue-100 px-2 py-1 mt-1">
          <Text variant="caption" color="secondary">
            AI confidence {confidence}%
          </Text>
        </View>
      </View>

      <View className="flex-row flex-wrap gap-2 mb-3">
        {MODEL_OPTIONS.map((option) => (
          <Button
            key={option.key}
            testID={`pricing-${option.key}`}
            title={option.label}
            variant={pricingModel === option.key ? "primary" : "outline"}
            onPress={() => setPricingModel(option.key)}
          />
        ))}
      </View>

      <ScrollView className="flex-1" contentContainerClassName="gap-3 pb-4" keyboardShouldPersistTaps="handled">
        {items.map((item, index) => (
          <View key={item.id} className="rounded-2xl border border-slate-200 bg-white p-3 gap-2 overflow-hidden">
            <View className="flex-row items-center justify-between">
              <Text variant="caption" color="secondary">
                Line {index + 1}
              </Text>
              <IconButton icon="close" size={18} color="#6B7280" onPress={() => removeItem(item.id)} />
            </View>

            <TextInput
              className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-900"
              value={item.description}
              onChangeText={(value) => updateItem(item.id, "description", value)}
              placeholder="Description"
            />

            <View className="flex-row flex-wrap gap-2">
              <View className="min-w-[70px] flex-1">
                <Text variant="caption" color="secondary">
                  Qty
                </Text>
                <TextInput
                  className="h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-900"
                  value={item.qty}
                  onChangeText={(value) => updateItem(item.id, "qty", value)}
                  keyboardType="decimal-pad"
                />
              </View>
              <View className="min-w-[70px] flex-1">
                <Text variant="caption" color="secondary">
                  Unit
                </Text>
                <TextInput
                  className="h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-900"
                  value={item.unit}
                  onChangeText={(value) => updateItem(item.id, "unit", value)}
                />
              </View>
              <View className="min-w-[100px] flex-[1.5]">
                <Text variant="caption" color="secondary">
                  Price (£)
                </Text>
                <TextInput
                  className="h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-900"
                  value={item.unitPrice}
                  onChangeText={(value) => updateItem(item.id, "unitPrice", value)}
                  keyboardType="decimal-pad"
                />
              </View>
            </View>
          </View>
        ))}

        <Button title="+ Add line item" variant="outline" onPress={addLine} />
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
        <View className="flex-row justify-between items-center">
          <Text variant="caption" color="secondary">
            Subtotal
          </Text>
          <Text variant="caption" color="secondary">
            £{totals.subtotal.toFixed(2)}
          </Text>
        </View>
        <View className="flex-row justify-between items-center">
          <Text variant="caption" color="secondary">
            VAT (20%)
          </Text>
          <Text variant="caption" color="secondary">
            £{totals.vat.toFixed(2)}
          </Text>
        </View>
        <View className="flex-row justify-between items-center mt-1">
          <Text variant="body" weight="bold">
            Total
          </Text>
          <Text variant="title" weight="bold">
            £{totals.total.toFixed(2)}
          </Text>
        </View>

        <Button
          title={seedQuote?.status === "sent" ? "Update quote" : isFromLead ? "Approve & send" : "Save changes"}
          onPress={onClose}
        />
        <Button
          testID="quote-request-info"
          title={seedQuote?.status === "sent" ? "Send follow-up" : "Request more info"}
          variant="outline"
          onPress={() => (resolvedLead ? setShowRequestInfo(true) : onClose())}
        />
      </View>
    </Screen>
  );
}
