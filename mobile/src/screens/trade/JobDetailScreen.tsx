import { useEffect, useMemo, useState } from "react";
import { Alert, Image, KeyboardAvoidingView, Linking, Modal, Platform, Pressable, ScrollView, TextInput, View } from "react-native";
import DateTimePicker from "@react-native-community/datetimepicker";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Text } from "../../components/ui/Text";
import { Screen } from "../../components/ui/Screen";
import { fetchQuote } from "../../api/quotes";
import { useQuoteRoundingIncrement } from "../../api/businesses";
import { ApiError } from "../../lib/apiClient";
import { formatMoneyGBP, roundUpToIncrement } from "../../lib/format";
import { Job, JobStatus } from "../../types";

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function toLocalIsoDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function toHHMM(d: Date): string {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return fallback;
}

const STATUS_COPY: Record<JobStatus, string> = {
  draft: "Draft",
  confirmed: "Confirmed",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

const STATUS_COLORS: Record<JobStatus, string> = {
  draft: "#FFFBEB", // warning surface — tentative until confirmed via the quote
  confirmed: "#E2E8EB", // info-100 slate
  in_progress: "#FFFBEB", // warning surface
  completed: "#ECFDF5", // success surface
  cancelled: "#FEF2F2", // error surface
};

type InvoiceItem = { id: string; description: string; amount: number };

type JobUpdatePatch = {
  notes?: string;
  assignedUserId?: string | null;
  /** ISO datetimes — scheduling/rescheduling the job. */
  scheduledStart?: string;
  scheduledEnd?: string;
};

type JobDetailScreenProps = {
  job: Job;
  /** Header back button — returns to the previous screen (quote-context nav). */
  onClose: () => void;
  /** Footer "Close" action after completion — exits to the dashboard tab. */
  onExitToDashboard: () => void;
  /** Persist the on-site line items as a real invoice. */
  onSubmitInvoice?: (
    lineItems: { description: string; amount: number }[],
    total: number
  ) => void | Promise<void>;
  /** Open the create-invoice page (prefilled from the job's quote when it has
   * one; AI-assisted draft for quote-less jobs). */
  onCreateInvoiceAi?: () => void;  /** Persist status transitions on the backend. */
  onStart?: () => Promise<void>;
  onComplete?: () => Promise<void>;
  /** Id of the invoice already created for this job's quote, when one exists. */
  existingInvoiceId?: string | null;
  /** VAT rate applied to ad-hoc invoice previews (from the source quote). */
  vatRate?: number;
  /** Navigate to the existing invoice. */
  onViewInvoice?: () => void;
  /** Persist notes/assignee changes (PATCH /jobs/{id}). */
  onUpdateJob?: (patch: JobUpdatePatch) => Promise<void>;
  /** Tenant staff members available for assignment. */
  members?: { id: string; fullName: string }[];
  /** Notes saved on the backend job record. */
  initialNotes?: string | null;
  /** Raw scheduled window from the backend job record (null when unscheduled). */
  scheduledStart?: string | null;
  scheduledEnd?: string | null;
  /** Photos carried over from the source quote. */
  photos?: string[];
  busy?: boolean;
  /** Customer contact details for the message button (N5 contact preference). */
  contactEmail?: string | null;
  preferredContactMethod?: string | null;
  /** True when the customer has a registered app account (in-app chat works). */
  hasAccount?: boolean;
  /** Open (find-or-create) the in-app chat thread with this customer. */
  onOpenChat?: () => Promise<void>;
};

export function JobDetailScreen({
  job,
  onClose,
  onExitToDashboard,
  onSubmitInvoice,
  onCreateInvoiceAi,
  onStart,
  onComplete,
  existingInvoiceId,
  vatRate,
  onViewInvoice,
  onUpdateJob,
  members,
  initialNotes,
  scheduledStart,
  scheduledEnd,
  photos,
  busy,
  contactEmail,
  preferredContactMethod,
  hasAccount,
  onOpenChat,
}: JobDetailScreenProps) {
  const [status, setStatus] = useState<JobStatus>(job.status);
  const [notes, setNotes] = useState(initialNotes ?? "");
  const [notesDirty, setNotesDirty] = useState(false);
  const [savingNotes, setSavingNotes] = useState(false);
  const [assignedTo, setAssignedTo] = useState(job.assignedTo);
  const [assigneePickerOpen, setAssigneePickerOpen] = useState(false);
  const [savingAssignee, setSavingAssignee] = useState(false);
  const [items, setItems] = useState<InvoiceItem[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [showSchedDatePicker, setShowSchedDatePicker] = useState(false);
  const [showSchedTimePicker, setShowSchedTimePicker] = useState(false);
  const [showSchedModal, setShowSchedModal] = useState(false);
  const [pendingSchedDate, setPendingSchedDate] = useState<Date>(new Date());
  const [schedDate, setSchedDate] = useState("");
  const [schedTime, setSchedTime] = useState("");
  const [savingSchedule, setSavingSchedule] = useState(false);

  // The job record loads asynchronously — adopt server notes until the user
  // starts editing.
  useEffect(() => {
    if (!notesDirty) setNotes(initialNotes ?? "");
  }, [initialNotes, notesDirty]);
  useEffect(() => setAssignedTo(job.assignedTo), [job.assignedTo]);

  // Quote-less jobs have no priced lines to inherit: the electrician builds the
  // invoice on the AI create-invoice page (or by hand below).
  const hasQuote = job.quoteId !== "";

  // The attributed quote's lines/totals seed the invoice summary; the backend
  // mirrors them exactly onto the invoice (rounding uplift included).
  const sourceQuoteQuery = useQuery({
    queryKey: ["quote", job.quoteId],
    queryFn: () => fetchQuote(job.quoteId),
    enabled: hasQuote,
  });
  const sourceQuote = sourceQuoteQuery.data;

  // Quote-less invoices are scratch invoices: the backend rounds the total up
  // once at creation per the tenant setting, so the preview must round too.
  const roundingIncrement = useQuoteRoundingIncrement();
  const totals = useMemo(() => {
    const subtotal = items.reduce((sum, i) => sum + i.amount, 0);
    const vat = subtotal * (vatRate ?? 0.2);
    const rawTotal = subtotal + vat;
    const total = roundUpToIncrement(rawTotal, roundingIncrement);
    return { subtotal, vat, uplift: total - rawTotal, total };
  }, [items, vatRate, roundingIncrement]);

  const handleStart = async () => {
    try {
      if (onStart) {
        await onStart();
      }
      setStatus("in_progress");
    } catch (err) {
      Alert.alert("Couldn't start the job", errorMessage(err, "Please try again."));
    }
  };

  const handleComplete = async () => {
    try {
      if (onComplete) {
        await onComplete();
      }
      setStatus("completed");
    } catch (err) {
      Alert.alert("Couldn't complete the job", errorMessage(err, "Please try again."));
    }
  };

  const handleSaveNotes = async () => {
    if (!onUpdateJob) return;
    setSavingNotes(true);
    try {
      await onUpdateJob({ notes });
      setNotesDirty(false);
    } catch (err) {
      Alert.alert("Couldn't save the notes", errorMessage(err, "Please try again."));
    } finally {
      setSavingNotes(false);
    }
  };

  const handleSelectAssignee = async (userId: string | null, name: string) => {
    setAssigneePickerOpen(false);
    if (!onUpdateJob) {
      setAssignedTo(name);
      return;
    }
    setSavingAssignee(true);
    try {
      await onUpdateJob({ assignedUserId: userId });
      setAssignedTo(name);
    } catch (err) {
      Alert.alert("Couldn't update the assignee", errorMessage(err, "Please try again."));
    } finally {
      setSavingAssignee(false);
    }
  };

  // Rescheduling keeps the job's current span; an unscheduled job gets 2h.
  const scheduleDurationMs = useMemo(() => {
    if (scheduledStart && scheduledEnd) {
      const span = new Date(scheduledEnd).getTime() - new Date(scheduledStart).getTime();
      if (span > 0) return span;
    }
    return 2 * 60 * 60 * 1000;
  }, [scheduledStart, scheduledEnd]);

  const openSchedulePicker = () => {
    const base = scheduledStart ? new Date(scheduledStart) : new Date();
    setPendingSchedDate(base);
    setSchedDate(toLocalIsoDate(base));
    setSchedTime(toHHMM(base));
    if (Platform.OS === "web") setShowSchedModal(true);
    else setShowSchedDatePicker(true);
  };

  const onSchedPickerValueChange = (_event: unknown, selected?: Date) => {
    if (selected) setPendingSchedDate(selected);
  };

  const saveSchedule = async (dateStr: string, timeStr: string) => {
    if (!onUpdateJob) return;
    const start = new Date(`${dateStr}T${timeStr}:00`);
    if (
      !/^\d{4}-\d{2}-\d{2}$/.test(dateStr) ||
      !/^\d{2}:\d{2}$/.test(timeStr) ||
      Number.isNaN(start.getTime())
    ) {
      Alert.alert("That date/time isn't valid", "Use YYYY-MM-DD for the date and HH:MM for the time.");
      return;
    }
    const end = new Date(start.getTime() + scheduleDurationMs);
    setSavingSchedule(true);
    try {
      await onUpdateJob({
        scheduledStart: start.toISOString(),
        scheduledEnd: end.toISOString(),
      });
      setShowSchedModal(false);
    } catch (err) {
      Alert.alert("Couldn't schedule the job", errorMessage(err, "Please try again."));
    } finally {
      setSavingSchedule(false);
    }
  };

  const handleSubmitInvoice = async () => {
    if (hasQuote && onCreateInvoiceAi) {
      // Jobs with an attributed quote build the invoice on the create-invoice
      // page, prefilled with the quote's lines/total (editable before send) —
      // never a blind £0.00 create-and-send from here.
      onCreateInvoiceAi();
      return;
    }
    if (!hasQuote && items.length === 0) {
      // N19: quote-less jobs build their invoice on the AI create-invoice page.
      if (onCreateInvoiceAi) {
        onCreateInvoiceAi();
        return;
      }
      Alert.alert(
        "No quote attached",
        "This job has no quote attached, so there are no priced lines to invoice. Add the job's line items above first, then create the invoice."
      );
      return;
    }
    setSubmitting(true);
    try {
      await onSubmitInvoice?.(
        items.map((i) => ({ description: i.description, amount: i.amount })),
        totals.total
      );
    } catch (err) {
      Alert.alert("Couldn't create the invoice", errorMessage(err, "Please try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const navigateToAddress = async () => {
    const address = encodeURIComponent(job.address);
    // Platform-default routing: on iOS the universal maps URL is handed to the
    // system, which opens the user's default maps app (Apple Maps if none was
    // chosen); elsewhere geo: lets Android pick. The Apple scheme is only the
    // last-resort fallback — never the first choice.
    const schemes =
      Platform.OS === "ios"
        ? [`https://maps.apple.com/?q=${address}`, `maps://?q=${address}`]
        : [
            `geo:0,0?q=${address}`,
            `https://www.google.com/maps/search/?api=1&query=${address}`,
          ];
    for (const url of schemes) {
      const can = await Linking.canOpenURL(url);
      if (can) {
        await Linking.openURL(url);
        return;
      }
    }
    Alert.alert("Cannot open maps", "No maps application is available on this device.");
  };

  const callCustomer = () =>
    Linking.openURL(`tel:${job.phone.replace(/\s/g, "")}`).catch(() =>
      Alert.alert("Cannot place call", "No dialler is available on this device.")
    );

  const textCustomer = () =>
    Linking.openURL(`sms:${job.phone.replace(/\s/g, "")}`).catch(() =>
      Alert.alert("Cannot send message", "No messaging app is available on this device.")
    );

  const emailCustomer = () =>
    Linking.openURL(`mailto:${contactEmail}`).catch(() =>
      Alert.alert("Cannot send email", "No mail app is available on this device.")
    );

  const openChat = async () => {
    if (!onOpenChat) return false;
    try {
      await onOpenChat();
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) return false;
      Alert.alert("Couldn't open the chat", errorMessage(err, "Please try again."));
      return true; // surfaced already — don't cascade into more fallbacks
    }
  };

  /**
   * N5: the message button honours the customer's preferred contact method.
   * in_app_chat → the in-app conversation; email → mailto:; phone → sms:.
   * Unset preference falls back to in-app chat (registered customers), then
   * email; each preference degrades the same way when its channel is missing.
   */
  const messageCustomer = async () => {
    const preference = preferredContactMethod ?? "";
    if (preference === "phone") {
      textCustomer();
      return;
    }
    if (preference === "email" && contactEmail) {
      await emailCustomer();
      return;
    }
    if (hasAccount && (await openChat())) return;
    if (contactEmail) {
      await emailCustomer();
      return;
    }
    Alert.alert(
      "No way to message",
      "This customer has no app account and no email address on file — try calling them instead."
    );
  };

  const addLineItem = () => {
    setItems((prev) => [
      ...prev,
      { id: Date.now().toString(), description: "", amount: 0 },
    ]);
  };

  const updateItem = (id: string, field: keyof InvoiceItem, value: string) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === id
          ? { ...item, [field]: field === "amount" ? parseFloat(value) || 0 : value }
          : item
      )
    );
  };

  return (
    <Screen>
      <Header title="Job detail" onBack={onClose} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
      <ScrollView
        className="flex-1"
        contentContainerClassName="gap-4 pb-4"
        keyboardShouldPersistTaps="handled"
      >
        <View className="flex-row items-center justify-between rounded-2xl bg-slate-100 p-4">
          <Text variant="body" weight="semibold" numberOfLines={1} className="flex-1">
            {job.title}
          </Text>
          <View className="rounded-lg px-2 py-1" style={{ backgroundColor: STATUS_COLORS[status] }}>
            <Text variant="caption" color="secondary">
              {STATUS_COPY[status].toUpperCase()}
            </Text>
          </View>
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          {scheduledStart ? (
            <>
              <Text variant="body" weight="semibold">
                {job.date}, {job.time}
                {job.endTime ? ` – ${job.endTime}` : ""}
              </Text>
              <Text variant="caption" color="secondary">
                {status === "confirmed" ? "Confirmed with customer" : "Status updated in app"}
              </Text>
              {onUpdateJob && status !== "cancelled" && status !== "completed" && (
                <Button
                  testID="job-reschedule-button"
                  title="Reschedule"
                  variant="outline"
                  size="sm"
                  onPress={openSchedulePicker}
                />
              )}
            </>
          ) : (
            <>
              <Text variant="body" weight="semibold">
                Not scheduled yet
              </Text>
              <Text variant="caption" color="secondary">
                Pick a date and time to put this job on the calendar.
              </Text>
              {onUpdateJob && status !== "cancelled" && status !== "completed" && (
                <Button
                  testID="job-schedule-button"
                  title={savingSchedule ? "Scheduling…" : "Schedule job"}
                  size="sm"
                  disabled={savingSchedule}
                  onPress={openSchedulePicker}
                />
              )}
            </>
          )}
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Customer
          </Text>
          <Text variant="body">{job.customerName}</Text>
          <Text variant="caption" color="secondary">
            {job.phone}
          </Text>
          <View className="flex-row gap-2 pt-1">
            <Button title="Call" variant="outline" size="sm" onPress={callCustomer} />
            <Button title="Message" variant="outline" size="sm" onPress={() => void messageCustomer()} />
          </View>
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Address
          </Text>
          <Text variant="body">{job.address}</Text>
          <Button testID="job-navigate" title="Navigate" onPress={navigateToAddress} />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <View className="flex-row items-center justify-between">
            <Text variant="body" weight="semibold">
              Assigned to
            </Text>
            {members && members.length > 0 && (
              <Pressable
                testID="job-assignee-edit"
                onPress={() => setAssigneePickerOpen((open) => !open)}
              >
                <Text variant="caption" color="primary">
                  {assigneePickerOpen ? "Done" : "Change"}
                </Text>
              </Pressable>
            )}
          </View>
          <Text testID="job-assignee-name" variant="body">
            {savingAssignee ? "Saving…" : assignedTo || "Unassigned"}
          </Text>
          {assigneePickerOpen && members && (
            <View className="flex-row flex-wrap gap-2">
              <Button
                testID="job-assignee-none"
                title="Unassigned"
                size="sm"
                variant={assignedTo === "" ? "primary" : "outline"}
                onPress={() => void handleSelectAssignee(null, "")}
              />
              {members.map((member) => (
                <Button
                  key={member.id}
                  testID={`job-assignee-${member.id}`}
                  title={member.fullName}
                  size="sm"
                  variant={assignedTo === member.fullName ? "primary" : "outline"}
                  onPress={() => void handleSelectAssignee(member.id, member.fullName)}
                />
              ))}
            </View>
          )}
        </View>

        {photos && photos.length > 0 && (
          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Photos
            </Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View className="flex-row gap-2">
                {photos.map((url, index) => (
                  <Image
                    key={url}
                    testID={`job-photo-${index}`}
                    source={{ uri: url }}
                    className="h-24 w-24 rounded-xl"
                    accessibilityLabel={`Job photo ${index + 1}`}
                  />
                ))}
              </View>
            </ScrollView>
          </View>
        )}

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Notes
          </Text>
          <TextInput
            testID="job-notes-input"
            className="min-h-20 rounded-xl border border-slate-200 bg-white p-3 text-base text-slate-900"
            value={notes}
            onChangeText={(value) => {
              setNotes(value);
              setNotesDirty(true);
            }}
            placeholder="Access details, AI assumptions, customer requests…"
            multiline
            textAlignVertical="top"
          />
          {onUpdateJob && notesDirty && (
            <Button
              testID="job-notes-save"
              title={savingNotes ? "Saving…" : "Save notes"}
              size="sm"
              disabled={savingNotes}
              onPress={() => void handleSaveNotes()}
            />
          )}
        </View>

        {status === "completed" && (
          <>
            {existingInvoiceId ? (
              <View className="rounded-2xl bg-slate-100 p-4 gap-2">
                <Text variant="body" weight="semibold">
                  Invoice
                </Text>
                <Text variant="caption" color="secondary">
                  An invoice already exists for this job's quote.
                </Text>
              </View>
            ) : (
            <View className="rounded-2xl bg-slate-100 p-4 gap-3">
              <View className="flex-row items-center justify-between">
                <Text variant="body" weight="semibold">
                  Invoice items
                </Text>
                <Text variant="caption" color="secondary">
                  {hasQuote ? "from approved quote" : "no quote attached"}
                </Text>
              </View>
              {hasQuote ? (
                <>
                  <Text variant="caption" color="secondary">
                    The quote's lines prefill the invoice — you can review and edit them on the
                    next screen before sending.
                  </Text>
                  {(sourceQuote?.lineItems ?? []).map((li, index) => (
                    <View key={li.id ?? index} className="flex-row justify-between gap-2">
                      <Text variant="caption" className="flex-1">
                        {li.description}
                      </Text>
                      <Text variant="caption" color="secondary">
                        {parseFloat(li.quantity) || 0} ×{" "}
                        {formatMoneyGBP(parseFloat(li.unitPrice) || 0)}
                      </Text>
                    </View>
                  ))}
                  {sourceQuote && (
                    <>
                      <View className="my-1 h-px bg-slate-200" />
                      <View className="flex-row justify-between">
                        <Text variant="caption" color="secondary">
                          Subtotal
                        </Text>
                        <Text variant="caption" color="secondary">
                          {formatMoneyGBP(parseFloat(sourceQuote.subtotal) || 0)}
                        </Text>
                      </View>
                      <View className="flex-row justify-between">
                        <Text variant="caption" color="secondary">
                          VAT
                        </Text>
                        <Text variant="caption" color="secondary">
                          {formatMoneyGBP(parseFloat(sourceQuote.vatAmount) || 0)}
                        </Text>
                      </View>
                      <View className="flex-row justify-between">
                        <Text variant="body" weight="bold">
                          Total
                        </Text>
                        <Text variant="title" weight="bold" color="primary">
                          {formatMoneyGBP(parseFloat(sourceQuote.total) || 0)}
                        </Text>
                      </View>
                    </>
                  )}
                </>
              ) : (
                <>
              <Text variant="caption" color="secondary">
                This job has no quote attached — add the job's line items below, or build the
                invoice with AI.
              </Text>
              {items.map((item) => (
                <View key={item.id} className="gap-2">
                  <TextInput
                    testID={`job-invoice-description-${item.id}`}
                    className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900"
                    value={item.description}
                    onChangeText={(value) => updateItem(item.id, "description", value)}
                    placeholder="Description"
                  />
                  <TextInput
                    testID={`job-invoice-amount-${item.id}`}
                    className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900"
                    value={item.amount.toString()}
                    onChangeText={(value) => updateItem(item.id, "amount", value)}
                    placeholder="Amount"
                    keyboardType="decimal-pad"
                  />
                </View>
              ))}

              <Button
                testID="job-add-variation"
                title="+ Add line item"
                variant="outline"
                size="sm"
                onPress={addLineItem}
              />

              <View className="my-1 h-px bg-slate-200" />
              <View className="flex-row justify-between">
                <Text variant="caption" color="secondary">
                  Subtotal
                </Text>
                <Text variant="caption" color="secondary">
                  £{totals.subtotal.toFixed(2)}
                </Text>
              </View>
              <View className="flex-row justify-between">
                <Text variant="caption" color="secondary">
                  VAT ({((vatRate ?? 0.2) * 100).toFixed(0)}%)
                </Text>
                <Text variant="caption" color="secondary">
                  £{totals.vat.toFixed(2)}
                </Text>
              </View>
              {totals.uplift > 0.004 && (
                <View className="flex-row justify-between">
                  <Text variant="caption" color="secondary">
                    Rounded up
                  </Text>
                  <Text variant="caption" color="secondary">
                    +£{totals.uplift.toFixed(2)}
                  </Text>
                </View>
              )}
              <View className="flex-row justify-between">
                <Text variant="body" weight="bold">
                  Total
                </Text>
                <Text variant="title" weight="bold" color="primary">
                  £{totals.total.toFixed(2)}
                </Text>
              </View>
                </>
              )}
            </View>
            )}
          </>
        )}
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
        {status === "confirmed" && (
          <Button
            testID="job-start"
            title={busy ? "Starting…" : "Start job"}
            disabled={busy}
            onPress={handleStart}
          />
        )}
        {status === "in_progress" && (
          <Button
            testID="job-complete"
            title={busy ? "Updating…" : "Mark complete"}
            disabled={busy}
            onPress={handleComplete}
          />
        )}
        {status === "completed" && (
          <>
            {existingInvoiceId ? (
              <Button
                testID="job-view-invoice"
                title="View invoice"
                variant="outline"
                onPress={onViewInvoice}
              />
            ) : (
              <>
                {!hasQuote && onCreateInvoiceAi && (
                  <Button
                    testID="job-create-invoice-ai"
                    title="Create invoice with AI"
                    onPress={onCreateInvoiceAi}
                  />
                )}
                <Button
                  testID="job-create-invoice"
                  title={
                    hasQuote
                      ? "Create invoice"
                      : submitting
                        ? "Creating invoice…"
                        : `Create & send invoice · £${totals.total.toFixed(2)}`
                  }
                  variant={!hasQuote && onCreateInvoiceAi ? "outline" : "primary"}
                  disabled={submitting}
                  onPress={handleSubmitInvoice}
                />
              </>
            )}
            <Button title="Close" variant="outline" onPress={onExitToDashboard} />
          </>
        )}
        {status === "cancelled" && (
          <Button title="Re-open" variant="outline" onPress={() => setStatus("confirmed")} />
        )}
      </View>
      </KeyboardAvoidingView>

      {Platform.OS === "web" ? (
        <Modal
          visible={showSchedModal}
          transparent
          animationType="fade"
          onRequestClose={() => setShowSchedModal(false)}
        >
          <Pressable
            className="flex-1 justify-center bg-black/40 p-4"
            onPress={() => setShowSchedModal(false)}
          >
            <Pressable className="gap-3 self-center rounded-3xl bg-white p-4" onPress={() => {}}>
              <Text variant="body" weight="semibold">
                {scheduledStart ? "Reschedule job" : "Schedule job"}
              </Text>
              <FormField
                testID="job-schedule-date"
                label="Date"
                value={schedDate}
                onChangeText={setSchedDate}
                placeholder="YYYY-MM-DD"
                autoCapitalize="none"
                maxLength={10}
              />
              <FormField
                testID="job-schedule-time"
                label="Start time"
                value={schedTime}
                onChangeText={setSchedTime}
                placeholder="HH:MM"
                autoCapitalize="none"
                maxLength={5}
              />
              <Button
                testID="job-schedule-save"
                title={savingSchedule ? "Saving…" : "Save"}
                disabled={savingSchedule}
                onPress={() => void saveSchedule(schedDate.trim(), schedTime.trim())}
              />
            </Pressable>
          </Pressable>
        </Modal>
      ) : (
        <>
          <Modal
            visible={showSchedDatePicker}
            transparent
            animationType="slide"
            onRequestClose={() => setShowSchedDatePicker(false)}
          >
            <Pressable
              className="flex-1 justify-end bg-black/40"
              onPress={() => setShowSchedDatePicker(false)}
            >
              <Pressable className="rounded-t-3xl bg-white pb-8" onPress={() => {}}>
                <View className="flex-row items-center justify-between px-4 py-3">
                  <Text variant="body" weight="semibold">
                    Job date
                  </Text>
                  <Pressable
                    testID="job-schedule-date-done"
                    onPress={() => {
                      setShowSchedDatePicker(false);
                      setShowSchedTimePicker(true);
                    }}
                  >
                    <Text variant="body" weight="semibold" color="primary">
                      Done
                    </Text>
                  </Pressable>
                </View>
                <DateTimePicker
                  value={pendingSchedDate}
                  mode="date"
                  display="spinner"
                  onChange={onSchedPickerValueChange}
                />
              </Pressable>
            </Pressable>
          </Modal>

          <Modal
            visible={showSchedTimePicker}
            transparent
            animationType="slide"
            onRequestClose={() => setShowSchedTimePicker(false)}
          >
            <Pressable
              className="flex-1 justify-end bg-black/40"
              onPress={() => setShowSchedTimePicker(false)}
            >
              <Pressable className="rounded-t-3xl bg-white pb-8" onPress={() => {}}>
                <View className="flex-row items-center justify-between px-4 py-3">
                  <Text variant="body" weight="semibold">
                    Start time
                  </Text>
                  <Pressable
                    testID="job-schedule-time-done"
                    onPress={() => {
                      setShowSchedTimePicker(false);
                      void saveSchedule(toLocalIsoDate(pendingSchedDate), toHHMM(pendingSchedDate));
                    }}
                  >
                    <Text variant="body" weight="semibold" color="primary">
                      Done
                    </Text>
                  </Pressable>
                </View>
                <DateTimePicker
                  value={pendingSchedDate}
                  mode="time"
                  display="spinner"
                  onChange={onSchedPickerValueChange}
                />
              </Pressable>
            </Pressable>
          </Modal>
        </>
      )}
    </Screen>
  );
}
