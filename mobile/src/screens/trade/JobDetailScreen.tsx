import { useMemo, useState } from "react";
import { Alert, Linking, ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { IconButton } from "../../components/ui/IconButton";
import { Text } from "../../components/ui/Text";
import { Screen } from "../../components/ui/Screen";
import { Job, JobStatus } from "../../types";

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

type JobDetailScreenProps = {
  job: Job;
  onClose: () => void;
  /** Persist the on-site line items as a real invoice. */
  onSubmitInvoice?: (
    lineItems: { description: string; amount: number }[],
    total: number
  ) => void | Promise<void>;
  /** Persist status transitions on the backend. */
  onStart?: () => Promise<void>;
  onComplete?: () => Promise<void>;
  /** Id of the invoice already created for this job's quote, when one exists. */
  existingInvoiceId?: string | null;
  /** VAT rate applied to ad-hoc invoice previews (from the source quote). */
  vatRate?: number;
  /** Navigate to the existing invoice. */
  onViewInvoice?: () => void;
  busy?: boolean;
};

export function JobDetailScreen({
  job,
  onClose,
  onSubmitInvoice,
  onStart,
  onComplete,
  existingInvoiceId,
  vatRate,
  onViewInvoice,
  busy,
}: JobDetailScreenProps) {
  const [status, setStatus] = useState<JobStatus>(job.status);
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<InvoiceItem[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const totals = useMemo(() => {
    const subtotal = items.reduce((sum, i) => sum + i.amount, 0);
    const vat = subtotal * (vatRate ?? 0.2);
    return { subtotal, vat, total: subtotal + vat };
  }, [items, vatRate]);

  const handleStart = async () => {
    if (onStart) {
      await onStart();
    }
    setStatus("in_progress");
  };

  const handleComplete = async () => {
    if (onComplete) {
      await onComplete();
    }
    setStatus("completed");
  };

  const handleSubmitInvoice = async () => {
    setSubmitting(true);
    try {
      await onSubmitInvoice?.(
        items.map((i) => ({ description: i.description, amount: i.amount })),
        totals.total
      );
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

  const callCustomer = () => Linking.openURL(`tel:${job.phone.replace(/\s/g, "")}`);
  const messageCustomer = () => Linking.openURL(`sms:${job.phone.replace(/\s/g, "")}`);

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
          <Text variant="body" weight="semibold">
            Assigned to
          </Text>
          <Text variant="body">{job.assignedTo}</Text>
        </View>

        {status === "completed" ? (
          <>
            <View className="rounded-2xl bg-slate-100 p-4 gap-2">
              <Text variant="body" weight="semibold">
                Completion notes
              </Text>
              <TextInput
                testID="job-completion-notes"
                className="min-h-20 rounded-xl border border-slate-200 bg-white p-3 text-base text-slate-900"
                value={notes}
                onChangeText={setNotes}
                multiline
                textAlignVertical="top"
              />
            </View>

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
                  from approved quote
                </Text>
              </View>
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
                  VAT (20%)
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
        ) : (
          <View className="rounded-2xl bg-slate-100 p-4 gap-2">
            <Text variant="body" weight="semibold">
              Notes
            </Text>
            <Text variant="body" color="secondary">
              Add any job notes here.
            </Text>
          </View>
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
              <Button
                testID="job-create-invoice"
                title={
                  submitting
                    ? "Creating invoice…"
                    : `Create & send invoice · £${totals.total.toFixed(2)}`
                }
                disabled={submitting}
                onPress={handleSubmitInvoice}
              />
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
