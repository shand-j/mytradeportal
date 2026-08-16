import { useMemo, useState } from "react";
import { Alert, Linking, ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { IconButton } from "../../components/ui/IconButton";
import { Text } from "../../components/ui/Text";
import { Screen } from "../../components/ui/Screen";
import { Job, JobStatus } from "../../types";

const TEAM = [
  { id: "1", name: "Demo Owner", role: "owner" },
  { id: "2", name: "Jane Engineer", role: "engineer" },
];

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

const BASE_ITEMS: InvoiceItem[] = [
  { id: "i1", description: "Consumer unit replacement (labour)", amount: 520 },
  { id: "i2", description: "Metal 12-way RCBO board + materials", amount: 180 },
  { id: "i3", description: "Call-out fee", amount: 45 },
];

const DEFAULT_NOTES =
  "Replaced consumer unit with a 12-way RCBO board and tested all circuits. " +
  "Fitted an extra double socket in the garage at the customer's request.";

type JobDetailScreenProps = {
  job: Job;
  onClose: () => void;
  onSubmitInvoice?: (total: number) => void;
};

export function JobDetailScreen({ job, onClose, onSubmitInvoice }: JobDetailScreenProps) {
  const [assignedTo, setAssignedTo] = useState(job.assignedTo);
  const [status, setStatus] = useState<JobStatus>(job.status);
  const [notes, setNotes] = useState(DEFAULT_NOTES);
  const [items, setItems] = useState<InvoiceItem[]>(BASE_ITEMS);
  const [variationAdded, setVariationAdded] = useState(false);

  const totals = useMemo(() => {
    const subtotal = items.reduce((sum, i) => sum + i.amount, 0);
    const vat = subtotal * 0.2;
    return { subtotal, vat, total: subtotal + vat };
  }, [items]);

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

  const addVariation = () => {
    if (variationAdded) return;
    setItems((prev) => [
      ...prev,
      { id: "var-1", description: "Additional double socket (fitted on site)", amount: 90 },
    ]);
    setVariationAdded(true);
  };

  const assignedMember = TEAM.find((member) => member.name === assignedTo) ?? TEAM[0];

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
          <Text variant="body">
            {assignedMember.name} ({assignedMember.role})
          </Text>
          <View className="flex-row flex-wrap gap-2">
            {TEAM.map((member) => (
              <Button
                key={member.id}
                title={member.name}
                size="sm"
                variant={assignedTo === member.name ? "primary" : "outline"}
                onPress={() => setAssignedTo(member.name)}
              />
            ))}
          </View>
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
                <View key={item.id} className="flex-row items-center justify-between gap-2">
                  <Text variant="body" style={{ flex: 1 }} numberOfLines={1}>
                    {item.description}
                  </Text>
                  <Text variant="body" weight="semibold">
                    £{item.amount.toFixed(2)}
                  </Text>
                </View>
              ))}

              {!variationAdded && (
                <Button
                  testID="job-add-variation"
                  title="+ Add on-site variation"
                  variant="outline"
                  size="sm"
                  onPress={addVariation}
                />
              )}

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
          </>
        ) : (
          <View className="rounded-2xl bg-slate-100 p-4 gap-2">
            <Text variant="body" weight="semibold">
              Notes
            </Text>
            <Text variant="body" color="secondary">
              Customer has a dog; board is in the garage. Access via side gate.
            </Text>
          </View>
        )}
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
        {status === "confirmed" && (
          <Button testID="job-start" title="Start job" onPress={() => setStatus("in_progress")} />
        )}
        {status === "in_progress" && (
          <Button
            testID="job-complete"
            title="Mark complete"
            onPress={() => setStatus("completed")}
          />
        )}
        {status === "completed" && (
          <>
            <Button
              testID="job-create-invoice"
              title={`Create & send invoice · £${totals.total.toFixed(2)}`}
              onPress={() => onSubmitInvoice?.(totals.total)}
            />
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
