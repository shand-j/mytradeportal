import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Animated, ActionSheetIOS, Platform, ScrollView, StyleProp, TextInput, View, ViewStyle } from "react-native";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { IconButton } from "../../components/ui/IconButton";
import { Screen } from "../../components/ui/Screen";
import { SelectableChip } from "../../components/ui/SelectableChip";
import { Text } from "../../components/ui/Text";
import { ContactCustomerCard } from "../../components/trade/ContactCustomerCard";
import { Lead, Quote, QuoteLineItem } from "../../types";
import { updateQuote, useRefineQuote, useSendQuote, useUpdateQuote } from "../../api/quotes";
import { useLead } from "../../api/quoteRequests";
import { startDirectThread } from "../../api/communications";
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

      {/* Assumptions / AI details placeholder */}
      <View className="rounded-xl bg-slate-100 p-3 gap-2">
        <PulseBlock style={{ height: 10, width: "78%" }} />
        <PulseBlock style={{ height: 10, width: "64%" }} />
        <PulseBlock style={{ height: 10, width: "71%" }} />
      </View>

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
  /** True once a sent/paid invoice exists for this quote: edit + refine lock. */
  invoicedReadOnly?: boolean;
};

export function QuoteEditScreen({
  lead,
  seed,
  onClose,
  onConvertToInvoice,
  onConvertToJob,
  existingJobId,
  jobConvertFailed,
  invoicedReadOnly,
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
  // A sent/paid invoice locks the quote server-side (409 quote_invoiced).
  const readOnly = !!invoicedReadOnly;

  // --- Debounced auto-save of line-item edits (real backend quotes only) ---
  const queryClient = useQueryClient();
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  // Snapshot of what the backend last saw. Null until the initial seed has
  // been recorded so mount never triggers a save.
  const lastSavedRef = useRef<QuoteLineItem[] | null>(null);
  // Next payload to persist: line items plus the VAT rate in effect when the
  // edit was made, so a VAT toggle queued mid-debounce is never lost.
  const pendingSaveRef = useRef<{ items: QuoteLineItem[]; vatRate: number } | null>(null);
  // Serialises saves so an auto-save never overlaps one already in flight.
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());

  // The tenant's registered rate, as captured on the quote at creation. A
  // per-quote override may only lower/remove VAT (0), never raise it.
  const tenantVatRate = seedQuote?.vatRate ?? 0.2;
  const [vatRate, setVatRate] = useState(tenantVatRate);
  // Show the VAT selector whenever the tenant is VAT-registered (either the
  // quote still carries the tenant rate, or it was previously zero-rated and
  // can be restored).
  const isVatRegistered = tenantVatRate > 0 || vatRate > 0;

  const runPendingSave = () => {
    if (!seedQuote || !isRealQuote || readOnly) return;
    saveChainRef.current = saveChainRef.current.then(async () => {
      // Another edit may have queued a newer snapshot while we waited.
      const current = pendingSaveRef.current;
      if (!current) return;
      setSaveState("saving");
      try {
        await updateQuote(seedQuote.id, current.items, current.vatRate);
        lastSavedRef.current = current.items;
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
    if (!isRealQuote || readOnly) return;
    if (!lastSavedRef.current) {
      lastSavedRef.current = items;
      return;
    }
    if (items === lastSavedRef.current) return;
    pendingSaveRef.current = { items, vatRate };
    const timer = setTimeout(runPendingSave, AUTOSAVE_DELAY_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, vatRate, isRealQuote]);

  /**
   * Switch between the tenant's registered rate and zero-rating (issue #110 —
   * fulfils the onboarding TaxVatStep "you'll confirm per quote" promise).
   * Persists immediately: a VAT toggle is a deliberate edit, not a keystroke,
   * so it must not wait for the line-item debounce.
   */
  const applyVatRate = (next: number) => {
    if (next === vatRate) return;
    setVatRate(next);
    if (!isRealQuote || readOnly) return;
    pendingSaveRef.current = { items, vatRate: next };
    runPendingSave();
  };

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
    if (canCreateJobFromQuote) {
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
  // Terminal statuses never offer convert actions — the quote's journey is over.
  const isTerminal =
    seedQuote?.status === "rejected" ||
    seedQuote?.status === "invoiced" ||
    seedQuote?.status === "cancelled";
  const acceptedDates = seedQuote?.acceptedDates ?? [];
  // Convert-to-invoice stays reachable for quotes that predate the
  // quote → job → invoice flow (sent quotes, or accepted quotes whose
  // convert-to-job hit a 409 without a resolvable job).
  const showConvertToInvoice =
    !!onConvertToInvoice &&
    !isTerminal &&
    seedQuote?.status !== "draft" &&
    !existingJobId &&
    (!isAccepted || !!jobConvertFailed);
  const showConvertToJob =
    !!onConvertToJob && !isTerminal && isAccepted && !existingJobId && !jobConvertFailed;
  // The iOS sheet's Job option routes to the prefilled job-create page, which
  // marks off-app-agreed sent quotes as accepted during conversion — so it can
  // be offered for sent quotes too. The web convert-to-job button converts in
  // place and stays approved-only.
  const canCreateJobFromQuote =
    !!onConvertToJob && !isTerminal && (isAccepted || isSent) && !existingJobId && !jobConvertFailed;

  const quoteRequestId = seedQuote?.quoteRequestId ?? resolvedLead?.id;
  const isRefining = refineQuoteMutation.isPending;

  // Reachability for the chat entry point below: the lead prop (quote-intake
  // flow) or the source quote request (quote detail flow). Only an explicit
  // `false` gates chat — older backends omit the field.
  const { lead: fetchedLead } = useLead(resolvedLead ? undefined : quoteRequestId);
  const chatLead = resolvedLead ?? fetchedLead;
  const chatUnavailable = chatLead?.customerReachable === false;

  // C7: "Request more info" opens the chat with the customer. Quotes without a
  // linked thread (legacy/lead-less quotes) find-or-create one via the CRM
  // contact; only contacts with no app account stay disabled.
  const customerContactId = seedQuote?.customerId;
  const canMessageCustomer = Boolean(quoteRequestId || customerContactId);
  const openCustomerChat = async () => {
    try {
      const threadId =
        quoteRequestId ??
        (customerContactId ? (await startDirectThread(customerContactId)).quoteRequestId : null);
      if (threadId) {
        router.push({ pathname: "/(trade)/messages", params: { quoteRequestId: threadId } });
      }
    } catch (err) {
      Alert.alert(
        "Couldn't open the chat",
        err instanceof ApiError ? err.detail : "Please try again."
      );
    }
  };

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

        {readOnly && (
          <View
            testID="quote-invoiced-readonly"
            className="rounded-xl border border-slate-200 bg-slate-100 p-3"
          >
            <Text variant="caption" color="secondary" align="center">
              Invoiced — read-only. The invoice has been sent, so this quote can no longer be edited.
            </Text>
          </View>
        )}

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
              {!readOnly && (
                <IconButton icon="close" size={18} color="#6B7280" onPress={() => removeItem(item.id)} />
              )}
            </View>

            <TextInput
              testID={`quote-line-description-${index}`}
              className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-900"
              value={item.description}
              onChangeText={(value) => updateItem(item.id, "description", value)}
              placeholder="Description"
              editable={!readOnly}
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
                  editable={!readOnly}
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
                  editable={!readOnly}
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
                  editable={!readOnly}
                />
              </View>
            </View>
          </View>
        ))}

        {!readOnly && <Button title="+ Add line item" variant="outline" onPress={addLine} />}
          </>
        )}

        {!readOnly && seedQuote?.aiGenerated && isRealQuote && (
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
        {isVatRegistered && !readOnly && (
          <View className="flex-row items-center justify-between gap-2">
            <Text variant="caption" color="secondary">
              VAT treatment
            </Text>
            <View className="flex-row gap-2">
              <SelectableChip
                testID="quote-vat-standard"
                label={`VAT ${(tenantVatRate * 100).toFixed(0)}%`}
                selected={vatRate !== 0}
                onPress={() => applyVatRate(tenantVatRate)}
              />
              <SelectableChip
                testID="quote-vat-zero-rated"
                label="Zero-rated 0%"
                selected={vatRate === 0}
                onPress={() => applyVatRate(0)}
              />
            </View>
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

        {!readOnly && (
          <Button
            testID="quote-save"
            title={updateQuoteMutation.isPending ? "Saving…" : "Save changes"}
            variant={isSent ? "primary" : "outline"}
            disabled={updateQuoteMutation.isPending || sendQuoteMutation.isPending || !isRealQuote}
            onPress={() => void handleSave()}
          />
        )}
        {!readOnly && !isSent && (
          <Button
            testID="quote-approve-send"
            title={sendQuoteMutation.isPending ? "Sending…" : "Send quote"}
            disabled={sendQuoteMutation.isPending || updateQuoteMutation.isPending || !isRealQuote}
            onPress={handleSend}
          />
        )}
        {chatUnavailable && chatLead ? (
          // No app account: chat never reaches this customer, so offer
          // phone/email follow-up instead of the chat entry point.
          <ContactCustomerCard
            name={chatLead.customerName}
            phone={chatLead.customerPhone}
            email={chatLead.customerEmail}
            preferredMethod={chatLead.contactPreferredMethod}
          />
        ) : (
          <>
            <Button
              testID="quote-request-info"
              title={isSent ? "Send follow-up" : "Request more info"}
              variant="outline"
              disabled={!canMessageCustomer}
              onPress={() => void openCustomerChat()}
            />
            {!canMessageCustomer && (
              <Text testID="quote-request-info-empty" variant="caption" color="secondary" align="center">
                No linked customer conversation
              </Text>
            )}
          </>
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
          (canCreateJobFromQuote || showConvertToInvoice) && (
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
