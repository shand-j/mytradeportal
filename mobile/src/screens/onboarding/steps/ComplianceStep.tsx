import { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import DateTimePicker from "@react-native-community/datetimepicker";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";

type ComplianceStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

function formatUkDate(date: Date): string {
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const year = date.getFullYear();
  return `${day}-${month}-${year}`;
}

function parseUkDate(value: string): Date | null {
  const match = value.match(/^\d{2}-\d{2}-\d{4}$/);
  if (!match) return null;
  const [day, month, year] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null;
  }
  return date;
}

const SCHEMES = [
  { key: "niceic", label: "NICEIC" },
  { key: "napit", label: "NAPIT" },
  { key: "elecsa", label: "Elecsa" },
  { key: "stroma", label: "Stroma" },
  { key: "besca", label: "Besca" },
  { key: "select_scotland", label: "Select Scotland" },
  { key: "none_yet", label: "None yet" },
];

const COVER_LEVELS = [
  { key: "1000000", label: "£1m" },
  { key: "2000000", label: "£2m" },
  { key: "5000000", label: "£5m" },
  { key: "10000000", label: "£10m" },
];

export function ComplianceStep({ data, onNext }: ComplianceStepProps) {
  const [scheme, setScheme] = useState((data?.scheme as string) ?? "");
  const [membership, setMembership] = useState((data?.membership as string) ?? "");
  const cpsStatus = (data?.cpsStatus as "self_declared" | "verified" | "pending") ?? "self_declared";
  const [bs7671, setBs7671] = useState((data?.bs7671 as boolean) ?? false);
  const [inspection, setInspection] = useState((data?.inspection as boolean) ?? false);
  const [insurer, setInsurer] = useState((data?.insurer as string) ?? "");
  const [policyNumber, setPolicyNumber] = useState((data?.policyNumber as string) ?? "");
  const [cover, setCover] = useState((data?.cover as string) ?? "");
  const [expiry, setExpiry] = useState((data?.expiry as string) ?? "");
  const [showDatePicker, setShowDatePicker] = useState(false);

  const onDateValueChange = (_event: unknown, selectedDate: Date) => {
    setShowDatePicker(false);
    setExpiry(formatUkDate(selectedDate));
  };

  const onDateDismiss = () => {
    setShowDatePicker(false);
  };

  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Compliance & credentials
        </Text>
        <Text variant="body" color="secondary">
          These build trust with customers and unlock customer-facing badges.
        </Text>

        <Text variant="body" weight="semibold">
          Competent Person Scheme
        </Text>
        <View className="flex-row flex-wrap gap-2">
          {SCHEMES.map((s) => (
            <Button
              key={s.key}
              title={s.label}
              variant={scheme === s.key ? "primary" : "outline"}
              onPress={() => setScheme(s.key)}
            />
          ))}
        </View>

        {scheme !== "none_yet" && scheme !== "" && (
          <FormField
            label="Membership number"
            value={membership}
            onChangeText={setMembership}
            placeholder="e.g. NE12345"
          />
        )}
        {scheme === "none_yet" && (
          <View className="rounded-2xl bg-amber-50 p-4">
            <Text variant="body" weight="semibold" color="warning">
              Provisional status
            </Text>
            <Text variant="caption" color="secondary">
              You can continue as provisional, but customer-facing quotes and AI auto-send are locked until you add a CPS.
            </Text>
          </View>
        )}

        <Text variant="body" weight="semibold">
          Qualifications
        </Text>
        <View className="flex-row flex-wrap gap-2">
          <Button
            title="18th Edition held"
            variant={bs7671 ? "primary" : "outline"}
            onPress={() => setBs7671((prev) => !prev)}
          />
          <Button
            title="Inspection & testing (2391)"
            variant={inspection ? "primary" : "outline"}
            onPress={() => setInspection((prev) => !prev)}
          />
        </View>

        <Text variant="body" weight="semibold">
          Public liability insurance
        </Text>
        <FormField
          label="Insurer"
          value={insurer}
          onChangeText={setInsurer}
          placeholder="e.g. AXA"
        />
        <FormField
          label="Policy number"
          value={policyNumber}
          onChangeText={setPolicyNumber}
          placeholder="e.g. PL-123456"
        />
        <Text variant="body" weight="semibold">
          Cover level
        </Text>
        <View className="flex-row flex-wrap gap-2">
          {COVER_LEVELS.map((c) => (
            <Button
              key={c.key}
              title={c.label}
              variant={cover === c.key ? "primary" : "outline"}
              onPress={() => setCover(c.key)}
            />
          ))}
        </View>
        <Text variant="body" weight="semibold">
          Expiry date
        </Text>
        <Pressable onPress={() => setShowDatePicker(true)}>
          <View className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <Text variant="body">{expiry || "DD-MM-YYYY"}</Text>
          </View>
        </Pressable>
        <Text variant="caption" color="secondary">
          Renewal reminder shown 30 days before expiry.
        </Text>
        {showDatePicker && (
          <DateTimePicker
            value={parseUkDate(expiry) ?? new Date()}
            mode="date"
            display="spinner"
            onValueChange={onDateValueChange}
            onDismiss={onDateDismiss}
          />
        )}

        <Button
          title="Continue"
          onPress={() =>
            onNext({
              scheme,
              membership,
              cpsStatus,
              bs7671,
              inspection,
              insurer,
              policyNumber,
              cover,
              expiry,
            })
          }
        />
      </View>
    </ScrollView>
  );
}
