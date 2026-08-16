import { useState } from "react";
import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";
import { VerificationBadge } from "../../../components/ui/VerificationBadge";

type TaxVatStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

export function TaxVatStep({ data, onNext }: TaxVatStepProps) {
  const [vatRegistered, setVatRegistered] = useState((data?.vatRegistered as boolean) ?? false);
  const [vatNumber, setVatNumber] = useState((data?.vatNumber as string) ?? "");
  const [scheme, setScheme] = useState((data?.scheme as string) ?? "standard");
  const [verifying, setVerifying] = useState(false);
  const [status, setStatus] = useState<"self_declared" | "verified" | "pending">(
    (data?.status as "self_declared" | "verified" | "pending") ?? "self_declared"
  );

  const handleVerify = () => {
    setVerifying(true);
    setTimeout(() => {
      setStatus("verified");
      setVerifying(false);
    }, 1200);
  };

  return (
    <ScrollView className="flex-1">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Tax & VAT
        </Text>
        <Text variant="body" color="secondary">
          We use this to show the right VAT on every quote.
        </Text>

        <Text variant="body" weight="semibold">
          Are you VAT registered?
        </Text>
        <View className="flex-row flex-wrap gap-2">
          <Button
            title="Yes"
            variant={vatRegistered ? "primary" : "outline"}
            onPress={() => setVatRegistered(true)}
          />
          <Button
            title="No"
            variant={!vatRegistered ? "primary" : "outline"}
            onPress={() => setVatRegistered(false)}
          />
        </View>

        {vatRegistered && (
          <View className="gap-4">
            <FormField
              label="VAT number"
              value={vatNumber}
              onChangeText={setVatNumber}
              placeholder="GB123456789"
              autoCapitalize="characters"
              maxLength={12}
            />

            <Button
              title={verifying ? "Verifying..." : "Verify VAT number"}
              variant="outline"
              onPress={handleVerify}
              disabled={vatNumber.length < 9 || verifying}
            />

            <VerificationBadge status={status} />

            <Text variant="body" weight="semibold">
              VAT scheme
            </Text>
            <View className="flex-row flex-wrap gap-2">
              <Button
                title="Standard"
                variant={scheme === "standard" ? "primary" : "outline"}
                onPress={() => setScheme("standard")}
              />
              <Button
                title="Flat rate"
                variant={scheme === "flat_rate" ? "primary" : "outline"}
                onPress={() => setScheme("flat_rate")}
              />
            </View>
          </View>
        )}

        <View className="rounded-2xl bg-slate-100 p-4">
          <Text variant="body" weight="semibold">
            Default VAT rate
          </Text>
          <Text variant="body" color="secondary">
            20% (read-only)
          </Text>
          <Text variant="caption" color="secondary">
            Some energy-saving materials may qualify for reduced VAT — you’ll confirm per quote.
          </Text>
        </View>

        <Button
          title="Continue"
          onPress={() =>
            onNext({
              vatRegistered,
              vatNumber,
              scheme,
              status,
              defaultRate: 0.2,
            })
          }
        />
      </View>
    </ScrollView>
  );
}
