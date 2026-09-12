import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Animated, ActionSheetIOS, Platform, ScrollView, StyleProp, TextInput, View, ViewStyle } from "react-native";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { IconButton } from "../../components/ui/IconButton";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { Lead, Quote, QuoteLineItem } from "../../types";
import { updateQuote, useRefineQuote, useSendQuote, useUpdateQuote } from "../../api/quotes";
import { ApiError } from "../../lib/apiClient";
import { formatMoneyGBP } from "../../lib/format";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Debounce window for line-item auto-save. */
const AUTOSAVE_DELAY_MS = 1500;

function buildItems(seed: Quote | undefined): QuoteLineItem[] {
  return (
    seed?.lineItems ?? [
      {
        id: Date.now().toString(),
        kind: "labour",
        description: "",
        qty: "1",
        unit: "item",
        unitPrice: "0.00",
        aiGenerated: false,
      },
    ]
  );
}

/** Pulsing slate-200 block used by the refine skeleton placeholder. */
function PulseBlock({ style }: { style?: StyleProp<ViewStyle> }) {
  const opacity = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.4, duration: 700, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 700, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);
  return (
    <Animated.View
      style={[{ backgroundColor: "#E2E8F0", borderRadius: 8 }, style, { opacity }]}
    />
  );
}

/** Skeleton rows shown in place of the line items while an AI refine runs. */
function RefineSkeleton() {
  return (
    <View testID="refine-skeleton" className="gap-3">
      <View
        testID="refine-banner"
        className="rounded-xl border border-primary-100 bg-primary-50 p-3"
      >
        <Text variant="caption" color="secondary" align="center">
          Regenerating… You can leave this page — you'll get a notification when the quote is ready.
        </Text>
      </View>

      <PulseBlock style={{ height: 56 }} />

      {[0, 1, 2].map((row) => (
        <View
          key={row}
          className="rounded-2xl border border-slate-200 bg-white p-3 gap-2"
        >
          <PulseBlock style={{ height: 12, width: "30%" }} />
          <PulseBlock style={{ height: 40 }} />
          <View className="flex-row gap-2">
            <PulseBlock style={{ height: 36, flex: 1 }} />
            <PulseBlock style={{ height: 36, flex: 1 }} />
            <PulseBlock style={{ height: 36, flex: 1.5 }} />
          </View>
        </View>
      ))}
    </View>
  );
}

export type QuoteEditScreenProps = {
  lead?: Lead;
  seed?: Quote;
  onClose: () => void;
  /** Connected mode: convert an approved/sent quote into an invoice. */
  onConvertToInvoice?: () => Promise<void>;
  /** Connected mode: convert an accepted quote into a scheduled job. */
  onConvertToJob?: () => Promise<void>;
  /** Id of the job already created from this quote, when one exists. */
  existingJobId?: string | null;
  /** True after convert-to-job 409'd without a resolvable job (legacy quote). */
  jobConvertFailed?: boolean;
};

export function QuoteEditScreen({
  lead,
  seed,
  onClose,
  onConvertToInvoice,
  onConvertToJob,
  existingJobId,
  jobConvertFailed,
}: QuoteEditScreenProps) {
  const router = useRouter();
  const seedQuote = seed;
  const resolvedLead = lead;

  const sendQuoteMutation = useSendQuote();
  const updateQuoteMutation = useUpdateQuote();
  const [items, setItems] = useState<QuoteLineItem[]>(() => buildItems(seedQuote));
  const [converting, setConverting] = useState(false);
  const refineQuoteMutation = useRefineQuote();
  const [refineInstructions, setRefineInstructions] = useState("");
  const [refineError, setRefineError] = useState<string | null>(null);

  const isRealQuote = !!seedQuote && UUID_RE.test(seedQuote.id);

  // --- Debounced auto-save of line-item edits (real backend quotes only) ---
  const queryClient = useQueryClient();
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  // Snapshot of what the backend last saw. Null until the initial seed has
  // been recorded so mount never triggers a save.
  const lastSavedRef = useRef<QuoteLineItem[] | null>(null);
  const pendingSaveRef = useRef<QuoteLineItem[] | null>(null);
  // Serialises saves so an auto-save never overlaps one already in flight.
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());

  const vatRate = seedQuote?.vatRate ?? 0.2;

  const runPendingSave = () => {
    if (!seedQuote || !isRealQuote) return;
    saveChainRef.current = saveChainRef.current.then(async () => {
      // Another edit may have queued a newer snapshot while we waited.
      const current = pendingSaveRef.current;
      if (!current) return;
      setSaveState("saving");
      try {
        await updateQuote(seedQuote.id, current, vatRate);
        lastSavedRef.current = current;
        pendingSaveRef.current = null;
        setSaveState("saved");
        queryClient.invalidateQueries({ queryKey: ["quotes"] });
        queryClient.invalidateQueries({ queryKey: ["quote", seedQuote.id] });
      } catch {
        setSaveState("error");
      }
    });
  };

  useEffect(() => {
    if (!isRealQuote) return;
    if (!lastSavedRef.current) {
      lastSavedRef.current = items;
      return;
    }
    if (items === lastSavedRef.current) return;
    pendingSaveRef.current = items;
    const timer = setTimeout(runPendingSave, AUTOSAVE_DELAY_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, isRealQuote]);

  /** Persist the current line items; cancels any queued auto-save of older edits. */
  const saveNow = async (): Promise<void> => {
    if (!isRealQuote) return;
    await updateQuoteMutation.mutateAsync({
      id: seedQuote.id,
      lineItems: items,
      vatRate,
    });
    // The manual save just persisted the current items — cancel any queued
    // auto-save of an older snapshot so it can't overwrite this write.
    pendingSaveRef.current = null;
    lastSavedRef.current = items;
    setSaveState("saved");
  };

  const handleSave = async () => {
    await saveNow();
    onClose();
  };

  const doSend = async () => {
    if (!isRealQuote) return;
    // Sending always includes the latest edits.
    await saveNow();
    await sendQuoteMutation.mutateAsync(seedQuote.id);
    onClose();
  };

  const handleSend = () => {
    // Alert.alert is a native-only API; on web the explicit button tap is the
    // confirmation (keeps the e2e flow working).
    if (Platform.OS === "web") {
      void doSend();
      return;
    }
    Alert.alert("Send quote?", `Send this quote to ${customerName}?`, [
      { text: "Cancel", style: "cancel" },
      { text: "Send", onPress: () => void doSend() },
    ]);
  };

  const handleConvertToInvoice = async () => {
    if (!onConvertToInvoice) return;
    setConverting(true);
    try {
      await onConvertToInvoice();
    } finally {
      setConverting(false);
    }
  };

  const handleConvertToJob = async () => {
    if (!onConvertToJob) return;
    setConverting(true);
    try {
      await onConvertToJob();
    } finally {
      setConverting(false);
    }
  };

  // iOS: one "Convert to…" button opens an ActionSheet; Job navigates to the
  // prefilled new-job page, Invoice converts in place.
  const handleConvertSheet = () => {
    if (!seedQuote) return;
    const actions: { label: string; run: () => void }[] = [];
    if (showConvertToJob) {
      actions.push({
        label: "Job",
        run: () => router.push({ pathname: "/(trade)/job/new", params: { quoteId: seedQuote.id } }),
      });
    }
    if (showConvertToInvoice) {
      actions.push({ label: "Invoice", run: () => void handleConvertToInvoice() });
    }
    ActionSheetIOS.showActionSheetWithOptions(
      {
        title: "Convert to…",
        options: ["Cancel", ...actions.map((a) => a.label)],
        cancelButtonIndex: 0,
      },
      (index) => {
        if (index > 0) actions[index - 1].run();
      }
    );
  };

  const handleRefine = async () => {
    if (!seedQuote) return;
    setRefineError(null);
    try {
      const updated = await refineQuoteMutation.mutateAsync({
        id: seedQuote.id,
        instructions: refineInstructions.trim(),
      });
      setItems(updated.lineItems);
      setRefineInstructions("");
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.detail
          : err instanceof Error
            ? err.message
            : "Couldn't refine the quote. Please try again.";
      setRefineError(message);
    }
  };

  const totals = useMemo(() => {
    const subtotal = items.reduce((sum, item) => {
      const qty = parseFloat(item.qty) || 0;
      const price = parseFloat(item.unitPrice) || 0;
      return sum + qty * price;
    }, 0);
    const vat = subtotal * vatRate;
    return { subtotal, vat, total: subtotal + vat };
  }, [items, vatRate]);

  const updateItem = (id: string, field: keyof QuoteLineItem, value: string) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, [field]: value } : item)));
  };

  const addLine = () => {
    setItems((prev) => [
      ...prev,
      { id: Date.now().toString(), kind: "labour", description: "", qty: "1", unit: "item", unitPrice: "0.00", aiGenerated: false },
    ]);
  };

  const removeItem = (id: string) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  };

  const title = resolvedLead?.title ?? seedQuote?.title ?? "Review quote";
  const postcode = resolvedLead?.postcode ?? seedQuote?.postcode ?? "—";
  const customerName = resolvedLead?.customerName ?? seedQuote?.customerName ?? "Customer";
  const confidence = seedQuote?.aiConfidence ?? null;

  const aiWarnings = seedQuote?.aiWarnings ?? [];
  const aiAssumptions = seedQuote?.aiAssumptions ?? [];
  const aiNotes = seedQuote?.aiNotes ?? null;
  const isCatalogueMiss =
    seedQuote?.retrievalStatus === "no_index" || seedQuote?.retrievalStatus === "skipped_no_key";
  const showAiDetails =
    aiWarnings.length > 0 || aiAssumptions.length > 0 || aiNotes != null || isCatalogueMiss;

  const isSent = seedQuote?.status === "sent";
  const isAccepted = seedQuote?.status === "accepted";
  const acceptedDates = seedQuote?.acceptedDates ?? [];
  // Convert-to-invoice stays reachable for quotes that predate the
  // quote → job → invoice flow (sent quotes, or accepted quotes whose
  // convert-to-job hit a 409 without a resolvable job).
  const showConvertToInvoice =
    !!onConvertToInvoice &&
    seedQuote?.status !== "draft" &&
    !existingJobId &&
    (!isAccepted || !!jobConvertFailed);
  const showConvertToJob =
    !!onConvertToJob && isAccepted && !existingJobId && !jobConvertFailed;

  const quoteRequestId = seedQuote?.quoteRequestId ?? resolvedLead?.id;
  const isRefining = refineQuoteMutation.isPending;

  return (
    <Screen>
      <Header testID="quote-edit-back" title="Review quote" onBack={onClose} />

      <ScrollView
        className="flex-1"
        style={{ minHeight: 0 }}
        contentContainerClassName="gap-3 pb-4"
        keyboardShouldPersistTaps="handled"
      >
        <View className="rounded-xl bg-slate-100 p-3 gap-1">
          <Text variant="body" weight="semibold">
            {title}
          </Text>
          <Text variant="caption" color="secondary">
            {customerName} · {postcode}
          </Text>
          {confidence != null && (
            <View className="self-start rounded-md bg-accent-100 px-2 py-1 mt-1">
              <Text variant="caption" color="secondary">
                AI confidence {Math.round(confidence * 100)}%
              </Text>
            </View>
          )}
        </View>

        {acceptedDates.length > 0 && (
          <View
            testID="quote-accepted-dates"
            className="rounded-xl border border-success-100 bg-success-50 p-3 gap-1"
          >
            <Text variant="caption" weight="semibold" color="secondary">
              Customer's confirmed dates
            </Text>
            <Text variant="caption" color="secondary">
              {acceptedDates.join(", ")}
            </Text>
          </View>
        )}

        {isRefining ? (
          <RefineSkeleton />
        ) : (
          <>
        {showAiDetails && (
          <View className="rounded-xl bg-amber-50 p-3 gap-2">
            {aiWarnings.map((warning) => (
              <Text key={warning} variant="caption" color="warning">
                • {warning}
              </Text>
            ))}
            {aiAssumptions.map((assumption) => (
              <Text key={assumption} variant="caption" color="secondary">
                • Assumed: {assumption}
              </Text>
            ))}
            {isCatalogueMiss && (
              <Text variant="caption" color="warning">
                Priced from AI knowledge — no catalogue match
              </Text>
            )}
            {aiNotes != null && (
              <Text variant="caption" color="secondary">
                {aiNotes}
              </Text>
            )}
          </View>
        )}

        {items.map((item, index) => (
          <View key={item.id} className="rounded-2xl border border-slate-200 bg-white p-3 gap-2">
            <View className="flex-row items-center justify-between">
              <View className="flex-row items-center gap-1">
                <Text variant="caption" color="secondary">
                  Line {index + 1}
                </Text>
                {item.aiGenerated && (
                  <Icon name="sparkles" size={12} color="#D97706" />
                )}
              </View>
              <IconButton icon="close" size={18} color="#6B7280" onPress={() => removeItem(item.id)} />
            </View>

            <TextInput
              testID={`quote-line-description-${index}`}
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
          </>
        )}

        {seedQuote?.aiGenerated && isRealQuote && (
          <View className="rounded-2xl border border-slate-200 bg-white p-3 gap-2">
            <Text variant="body" weight="semibold">
              Refine with AI
            </Text>
            <TextInput
              testID="refine-instructions"
              className="h-20 rounded-lg border border-slate-200 px-3 pt-2 text-sm text-slate-900"
              value={refineInstructions}
              onChangeText={setRefineInstructions}
              placeholder="e.g. Add a second consumer unit, reduce labour to 4 hours..."
              multiline
              textAlignVertical="top"
            />
            {refineError && (
              <View className="rounded-2xl bg-amber-50 p-3">
                <Text testID="refine-error" variant="caption" color="warning">
                  {refineError}
                </Text>
              </View>
            )}
            <Button
              testID="refine-submit"
              title={refineQuoteMutation.isPending ? "Refining…" : "Refine quote"}
              size="sm"
              disabled={refineQuoteMutation.isPending || !refineInstructions.trim()}
              onPress={handleRefine}
            />
          </View>
        )}
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-3 pb-2 gap-3">
        {isRealQuote && saveState !== "idle" && (
          <View className="flex-row items-center justify-between gap-2">
            <Text
              testID="quote-autosave-status"
              variant="caption"
              color={saveState === "error" ? "warning" : "secondary"}
            >
              {saveState === "saving"
                ? "Saving…"
                : saveState === "saved"
                  ? "Saved ✓"
                  : "Couldn't save your changes."}
            </Text>
            {saveState === "error" && (
              <Button
                testID="quote-autosave-retry"
                title="Retry"
                variant="outline"
                size="sm"
                onPress={runPendingSave}
              />
            )}
          </View>
        )}
        <View className="flex-row items-end justify-between gap-3">
          {isRefining ? (
            <PulseBlock style={{ height: 40, flex: 1 }} />
          ) : (
            <>
          <View>
            <Text variant="caption" color="secondary">
              Subtotal
            </Text>
            <Text variant="caption" color="secondary">
              {formatMoneyGBP(totals.subtotal)}
            </Text>
          </View>
          <View>
            <Text variant="caption" color="secondary">
              VAT ({(vatRate * 100).toFixed(0)}%)
            </Text>
            <Text variant="caption" color="secondary">
              {formatMoneyGBP(totals.vat)}
            </Text>
          </View>
          <View className="items-end">
            <Text variant="caption" color="secondary">
              Total
            </Text>
            <Text variant="title" weight="bold">
              {formatMoneyGBP(totals.total)}
            </Text>
          </View>
            </>
          )}
        </View>

        <Button
          testID="quote-save"
          title={updateQuoteMutation.isPending ? "Saving…" : "Save changes"}
          variant={isSent ? "primary" : "outline"}
          disabled={updateQuoteMutation.isPending || sendQuoteMutation.isPending || !isRealQuote}
          onPress={() => void handleSave()}
        />
        {!isSent && (
          <Button
            testID="quote-approve-send"
            title={sendQuoteMutation.isPending ? "Sending…" : "Send quote"}
            disabled={sendQuoteMutation.isPending || updateQuoteMutation.isPending || !isRealQuote}
            onPress={handleSend}
          />
        )}
        <Button
          testID="quote-request-info"
          title={isSent ? "Send follow-up" : "Request more info"}
          variant="outline"
          disabled={!quoteRequestId}
          onPress={() => {
            if (!quoteRequestId) return;
            router.push({ pathname: "/(trade)/messages", params: { quoteRequestId } });
          }}
        />
        {!quoteRequestId && (
          <Text testID="quote-request-info-empty" variant="caption" color="secondary" align="center">
            No linked customer conversation
          </Text>
        )}

        {existingJobId && (
          <Button
            testID="quote-view-job"
            title="View job"
            variant="outline"
            onPress={() => router.push(`/(trade)/job/${existingJobId}`)}
          />
        )}
        {Platform.OS === "web" ? (
          <>
            {showConvertToJob && (
              <Button
                testID="quote-convert-job"
                title={converting ? "Converting…" : "Convert to job"}
                disabled={converting}
                onPress={handleConvertToJob}
              />
            )}
            {showConvertToInvoice && (
              <Button
                testID="quote-convert-invoice"
                title={converting ? "Converting…" : "Convert to invoice"}
                variant="outline"
                disabled={converting}
                onPress={handleConvertToInvoice}
              />
            )}
          </>
        ) : (
          (showConvertToJob || showConvertToInvoice) && (
            <Button
              testID="quote-convert"
              title={converting ? "Converting…" : "Convert to…"}
              disabled={converting}
              onPress={handleConvertSheet}
            />
          )
        )}
      </View>
    </Screen>
  );
}
