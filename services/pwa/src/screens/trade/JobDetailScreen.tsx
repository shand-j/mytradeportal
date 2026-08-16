import { useState } from "react";
import { Alert, Linking, ScrollView, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
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

type JobDetailScreenProps = {
  job: Job;
  onClose: () => void;
  onCreateInvoice?: () => void;
};

export function JobDetailScreen({ job, onClose, onCreateInvoice }: JobDetailScreenProps) {
  const [assignedTo, setAssignedTo] = useState(job.assignedTo);
  const [status, setStatus] = useState<JobStatus>(job.status);

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

  const callCustomer = () => {
    Linking.openURL(`tel:${job.phone.replace(/\s/g, "")}`);
  };

  const messageCustomer = () => {
    Linking.openURL(`sms:${job.phone.replace(/\s/g, "")}`);
  };

  const assignedMember = TEAM.find((member) => member.name === assignedTo) ?? TEAM[0];

  const handleCreateInvoice = () => {
    Alert.alert("Create invoice?", "This will create a draft invoice for the job.", [
      { text: "Cancel", style: "cancel" },
      { text: "Create", onPress: onCreateInvoice },
    ]);
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
          <Button title="Navigate" onPress={navigateToAddress} />
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

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Notes
          </Text>
          <Text variant="body" color="secondary">
            Customer has a dog; board is in the garage. Access via side gate.
          </Text>
        </View>
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
        {status === "confirmed" && <Button title="Start job" onPress={() => setStatus("in_progress")} />}
        {status === "in_progress" && <Button title="Mark complete" onPress={() => setStatus("completed")} />}
        {status === "completed" && (
          <>
            <Button title="Create invoice" onPress={handleCreateInvoice} />
            <Button title="Close" variant="outline" onPress={onClose} />
          </>
        )}
        {status === "cancelled" && <Button title="Re-open" variant="outline" onPress={() => setStatus("confirmed")} />}
      </View>
    </Screen>
  );
}
