import { useState } from "react";
import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { FileUploadMock } from "../../../components/ui/FileUploadMock";
import { Text } from "../../../components/ui/Text";
import { VerificationBadge } from "../../../components/ui/VerificationBadge";

type ComplianceStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

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
  const [scheme, setScheme] = useState((data?.scheme as string) ?? "napit");
  const [membership, setMembership] = useState((data?.membership as string) ?? "NE12345");
  const [cpsStatus, setCpsStatus] = useState<"self_declared" | "verified" | "pending">(
    (data?.cpsStatus as "self_declared" | "verified" | "pending") ?? "self_declared"
  );
  const [bs7671, setBs7671] = useState((data?.bs7671 as boolean) ?? true);
  const [inspection, setInspection] = useState((data?.inspection as boolean) ?? true);
  const [insurer, setInsurer] = useState((data?.insurer as string) ?? "AXA");
  const [policyNumber, setPolicyNumber] = useState((data?.policyNumber as string) ?? "PL-123");
  const [cover, setCover] = useState((data?.cover as string) ?? "2000000");
  const [expiry, setExpiry] = useState((data?.expiry as string) ?? "2027-08-15");
  const [verifying, setVerifying] = useState(false);

  const handleVerifyCps = () => {
    setVerifying(true);
    setTimeout(() => {
      setCpsStatus("verified");
      setVerifying(false);
    }, 1200);
  };

  const schemeLabel = SCHEMES.find((s) => s.key === scheme)?.label ?? scheme;

  return (
    <ScrollView className="flex-1">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Compliance & credentials
        </Text>
        <Text variant="body" color="secondary">
          These build trust with customers and unlock customer-facing badges.
        </Text>

        <View className="rounded-2xl bg-slate-100 p-4">
          <Text variant="body" weight="semibold">
            Badges so far
          </Text>
          <View className="mt-2 flex-row flex-wrap gap-2">
            <VerificationBadge status={cpsStatus} label={`CPS ${schemeLabel}`} />
            <VerificationBadge status={bs7671 ? "verified" : "self_declared"} label="18th Edition" />
          </View>
        </View>

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

        {scheme !== "none_yet" ? (
          <View className="gap-3">
            <FormField
              label="Membership number"
              value={membership}
              onChangeText={setMembership}
              placeholder="e.g. NE12345"
            />
            <Button
              title={verifying ? "Verifying..." : "Verify membership"}
              variant="outline"
              onPress={handleVerifyCps}
              disabled={!membership || verifying}
            />
            <VerificationBadge status={cpsStatus} label={`CPS ${schemeLabel}`} />
          </View>
        ) : (
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
        <FileUploadMock label="Upload 18th Edition certificate" fileName="bs7671.pdf" />

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
        <FormField
          label="Expiry date"
          value={expiry}
          onChangeText={setExpiry}
          placeholder="YYYY-MM-DD"
          helper="Renewal reminder shown 30 days before expiry."
        />
        <FileUploadMock label="Upload insurance certificate" fileName="insurance.pdf" />

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
