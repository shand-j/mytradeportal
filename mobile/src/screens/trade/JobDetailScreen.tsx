import { useEffect, useMemo, useState } from "react";
import { Alert, Image, Linking, Pressable, ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Text } from "../../components/ui/Text";
import { Screen } from "../../components/ui/Screen";
import { ApiError } from "../../lib/apiClient";
import { Job, JobStatus } from "../../types";

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return fallback;
}

const STATUS_COPY: Record<JobStatus, string> = {
  confirmed: "Confirmed",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

const STATUS_COLORS: Record<JobStatus, string> = {
  confirmed: "#DBEAFE",
  in_progress: "#FEF3C7",
  completed: "#D1FAE5",
  cancelled: "#FEE2E2",
};

type InvoiceItem = { id: string; description: string; amount: number };

type JobUpdatePatch = { notes?: string; assignedUserId?: string | null };

type JobDetailScreenProps = {
  job: Job;
  onClose: () => void;
  /** Persist the on-site line items as a real invoice. */
  onSubmitInvoice?: (
    lineItems: { description: string; amount: number }[],
    total: number
  ) => void | Promise<void>;
  /** Quote-less jobs: open the AI create-invoice page. */
  onCreateInvoiceAi?: () => void;
  /** Persist status transitions on the backend. */
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
  /** Photos carried over from the source quote. */
  photos?: string[];
  busy?: boolean;
};

export function JobDetailScreen({
  job,
  onClose,
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
  photos,
  busy,
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

  // The job record loads asynchronously — adopt server notes until the user
  // starts editing.
  useEffect(() => {
    if (!notesDirty) setNotes(initialNotes ?? "");
  }, [initialNotes, notesDirty]);
  useEffect(() => setAssignedTo(job.assignedTo), [job.assignedTo]);

  // Quote-less jobs have no priced lines to inherit: the electrician builds the
  // invoice on the AI create-invoice page (or by hand below).
  const hasQuote = job.quoteId !== "";

  const totals = useMemo(() => {
    const subtotal = items.reduce((sum, i) => sum + i.amount, 0);
    const vat = subtotal * (vatRate ?? 0.2);
    return { subtotal, vat, total: subtotal + vat };
  }, [items, vatRate]);

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

  const handleSubmitInvoice = async () => {
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
    const schemes = [`maps://?q=${address}`, `http://maps.apple.com/?q=${address}`];
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
  const messageCustomer = () =>
    Linking.openURL(`sms:${job.phone.replace(/\s/g, "")}`).catch(() =>
      Alert.alert("Cannot send message", "No messaging app is available on this device.")
    );

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

      <ScrollView className="flex-1" contentContainerClassName="gap-4 pb-4">
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
          <Text variant="body" weight="semibold">
            {job.date}, {job.time}
          </Text>
          <Text variant="caption" color="secondary">
            {status === "confirmed" ? "Confirmed with customer" : "Status updated in app"}
          </Text>
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
            <Button title="Message" variant="outline" size="sm" onPress={messageCustomer} />
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
              {!hasQuote && (
                <Text variant="caption" color="secondary">
                  This job has no quote attached — add the job's line items below, or build the
                  invoice with AI.
                </Text>
              )}
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
              <View className="flex-row justify-between">
                <Text variant="body" weight="bold">
                  Total
                </Text>
                <Text variant="title" weight="bold" color="primary">
                  £{totals.total.toFixed(2)}
                </Text>
              </View>
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
                    submitting
                      ? "Creating invoice…"
                      : `Create & send invoice · £${totals.total.toFixed(2)}`
                  }
                  variant={!hasQuote && onCreateInvoiceAi ? "outline" : "primary"}
                  disabled={submitting}
                  onPress={handleSubmitInvoice}
                />
              </>
            )}
            <Button title="Close" variant="outline" onPress={onClose} />
          </>
        )}
        {status === "cancelled" && (
          <Button title="Re-open" variant="outline" onPress={() => setStatus("confirmed")} />
        )}
      </View>
    </Screen>
  );
}
