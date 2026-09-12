import { useMemo, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { IconButton } from "../../components/ui/IconButton";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { generateQuoteForContact } from "../../api/quotes";
import { createInvoice } from "../../api/invoices";
import { ApiError } from "../../lib/apiClient";
import { formatMoneyGBP } from "../../lib/format";

type EditableLine = {
  id: string;
  description: string;
  qty: string;
  unitPrice: string;
};

function blankLine(): EditableLine {
  return { id: Date.now().toString(), description: "", qty: "1", unitPrice: "0.00" };
}

export type InvoiceCreateScreenProps = {
  /** Job the invoice is for (quote-less jobs reach this page). */
  jobId?: string;
  contactId: string;
  /** Job title — seeds the AI description. */
  jobTitle?: string;
  customerName?: string;
  onClose: () => void;
};

/**
 * AI create-invoice page for jobs without a quote. Reuses the quote-generation
 * pipeline (AI lines, editable) but the CTA creates an invoice directly, then
 * hands off to the invoice page for review + sending.
 */
export function InvoiceCreateScreen({
  jobId,
  contactId,
  jobTitle,
  customerName,
  onClose,
}: InvoiceCreateScreenProps) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [description, setDescription] = useState(jobTitle ?? "");
  const [lines, setLines] = useState<EditableLine[]>([blankLine()]);
  const [generatedQuoteId, setGeneratedQuoteId] = useState<string | null>(null);
  const [vatRate, setVatRate] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const subtotal = useMemo(
    () =>
      lines.reduce((sum, line) => {
        const qty = parseFloat(line.qty) || 0;
        const price = parseFloat(line.unitPrice) || 0;
        return sum + qty * price;
      }, 0),
    [lines]
  );

  const updateLine = (id: string, field: keyof EditableLine, value: string) => {
    setLines((prev) => prev.map((line) => (line.id === id ? { ...line, [field]: value } : line)));
  };

  const removeLine = (id: string) => {
    setLines((prev) => prev.filter((line) => line.id !== id));
  };

  const handleGenerate = async () => {
    if (description.trim().length < 5) {
      setError("Describe the work in a few words so the AI can price it.");
      return;
    }
    setError(null);
    setGenerating(true);
    try {
      const quote = await generateQuoteForContact({
        contactId,
        description: description.trim(),
      });
      setGeneratedQuoteId(quote.id);
      const parsedVat = parseFloat(quote.vatRate);
      setVatRate(Number.isFinite(parsedVat) ? parsedVat : null);
      setLines(
        (quote.lineItems ?? []).map((li) => ({
          id: li.id,
          description: li.description,
          qty: String(li.quantity),
          unitPrice: String(li.unitPrice),
        }))
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : "Couldn't generate the invoice lines. Please try again."
      );
    } finally {
      setGenerating(false);
    }
  };

  const handleCreate = async () => {
    setError(null);
    const validLines = lines.filter((line) => line.description.trim() !== "");
    if (!generatedQuoteId && validLines.length === 0) {
      setError("Generate lines with AI or add at least one line item.");
      return;
    }
    setCreating(true);
    try {
      const invoice = await createInvoice({
        contactId,
        jobId,
        quoteId: generatedQuoteId ?? undefined,
        lineItems: validLines.map((line) => ({
          description: line.description.trim(),
          quantity: parseFloat(line.qty) || 1,
          unitPrice: parseFloat(line.unitPrice) || 0,
        })),
      });
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      router.replace(`/(trade)/invoice/${invoice.id}`);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Couldn't create the invoice. Please try again."
      );
    } finally {
      setCreating(false);
    }
  };

  return (
    <Screen>
      <Header testID="invoice-create-back" title="New invoice" onBack={onClose} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          className="flex-1"
          style={{ minHeight: 0 }}
          contentContainerClassName="gap-3 pb-4"
          keyboardShouldPersistTaps="handled"
        >
          <View className="rounded-xl bg-slate-100 p-3 gap-1">
            <Text variant="body" weight="semibold">
              {jobTitle ?? "Invoice"}
            </Text>
            {customerName ? (
              <Text variant="caption" color="secondary">
                {customerName}
              </Text>
            ) : null}
          </View>

          <View className="rounded-2xl border border-slate-200 bg-white p-3 gap-2">
            <Text variant="body" weight="semibold">
              Build with AI
            </Text>
            <TextInput
              testID="invoice-ai-description"
              className="h-20 rounded-lg border border-slate-200 px-3 pt-2 text-sm text-slate-900"
              value={description}
              onChangeText={setDescription}
              placeholder="Describe the work done, e.g. Replaced consumer unit and added two sockets…"
              multiline
              textAlignVertical="top"
            />
            <Button
              testID="invoice-ai-generate"
              title={generating ? "Generating…" : "Generate line items"}
              size="sm"
              disabled={generating}
              onPress={() => void handleGenerate()}
            />
          </View>

          {lines.map((line, index) => (
            <View
              key={line.id}
              className="rounded-2xl border border-slate-200 bg-white p-3 gap-2"
            >
              <View className="flex-row items-center justify-between">
                <View className="flex-row items-center gap-1">
                  <Text variant="caption" color="secondary">
                    Line {index + 1}
                  </Text>
                  {generatedQuoteId && <Icon name="sparkles" size={12} color="#D97706" />}
                </View>
                <IconButton
                  icon="close"
                  size={18}
                  color="#6B7280"
                  onPress={() => removeLine(line.id)}
                />
              </View>

              <TextInput
                testID={`invoice-line-description-${index}`}
                className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-900"
                value={line.description}
                onChangeText={(value) => updateLine(line.id, "description", value)}
                placeholder="Description"
              />

              <View className="flex-row gap-2">
                <View className="flex-1">
                  <Text variant="caption" color="secondary">
                    Qty
                  </Text>
                  <TextInput
                    testID={`invoice-line-qty-${index}`}
                    className="h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-900"
                    value={line.qty}
                    onChangeText={(value) => updateLine(line.id, "qty", value)}
                    keyboardType="decimal-pad"
                  />
                </View>
                <View className="flex-[1.5]">
                  <Text variant="caption" color="secondary">
                    Price (£)
                  </Text>
                  <TextInput
                    testID={`invoice-line-price-${index}`}
                    className="h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-900"
                    value={line.unitPrice}
                    onChangeText={(value) => updateLine(line.id, "unitPrice", value)}
                    keyboardType="decimal-pad"
                  />
                </View>
              </View>
            </View>
          ))}

          <Button
            testID="invoice-add-line"
            title="+ Add line item"
            variant="outline"
            onPress={() => setLines((prev) => [...prev, blankLine()])}
          />

          {error && (
            <View className="rounded-2xl bg-amber-50 p-3">
              <Text testID="invoice-create-error" variant="caption" color="warning">
                {error}
              </Text>
            </View>
          )}
        </ScrollView>

        <View className="border-t border-slate-200 bg-white pt-3 pb-2 gap-3">
          <View className="flex-row items-end justify-between gap-3">
            <View>
              <Text variant="caption" color="secondary">
                Subtotal
              </Text>
              <Text variant="caption" color="secondary">
                {formatMoneyGBP(subtotal)}
              </Text>
            </View>
            <View className="items-end">
              <Text variant="caption" color="secondary">
                {vatRate !== null
                  ? `Total incl. VAT (${(vatRate * 100).toFixed(0)}%)`
                  : "VAT is applied per your registration"}
              </Text>
              <Text variant="title" weight="bold">
                {vatRate !== null ? formatMoneyGBP(subtotal * (1 + vatRate)) : formatMoneyGBP(subtotal)}
              </Text>
            </View>
          </View>
          <Button
            testID="invoice-create-submit"
            title={creating ? "Creating…" : "Create invoice"}
            disabled={creating || generating}
            onPress={() => void handleCreate()}
          />
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
