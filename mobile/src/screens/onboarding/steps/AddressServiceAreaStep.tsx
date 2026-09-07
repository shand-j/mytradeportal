import { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";
import { VerificationBadge } from "../../../components/ui/VerificationBadge";

type AddressServiceAreaStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

const NATIONS = [
  { key: "england", label: "England" },
  { key: "wales", label: "Wales" },
  { key: "scotland", label: "Scotland" },
  { key: "northern_ireland", label: "Northern Ireland" },
];

export function AddressServiceAreaStep({ data, onNext }: AddressServiceAreaStepProps) {
  const [postcode, setPostcode] = useState((data?.postcode as string) ?? "");
  const [address, setAddress] = useState((data?.address as string) ?? "");
  const [mode, setMode] = useState<"radius" | "postcode_list">((data?.mode as "radius" | "postcode_list") ?? "radius");
  const [radius, setRadius] = useState((data?.radius as string) ?? "15");
  const [sectors, setSectors] = useState((data?.sectors as string) ?? "");
  const [nations, setNations] = useState<Set<string>>(new Set((data?.nations as string[]) ?? ["england"]));

  const toggleNation = (key: string) => {
    setNations((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <ScrollView className="flex-1">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Address & service area
        </Text>
        <Text variant="body" color="secondary">
          This is where you work and the area you serve.
        </Text>

        <FormField
          label="Trading postcode"
          value={postcode}
          onChangeText={setPostcode}
          placeholder="e.g. SK8 3NJ"
          autoCapitalize="characters"
          maxLength={8}
          helper="Customers outside this area will see a polite decline."
        />

        <FormField
          label="Trading address"
          value={address}
          onChangeText={setAddress}
          placeholder="Full trading address"
          multiline
        />

        <Text variant="body" weight="semibold">
          Service area mode
        </Text>
        <View className="flex-row flex-wrap gap-2">
          <Button
            title="Radius from base"
            variant={mode === "radius" ? "primary" : "outline"}
            onPress={() => setMode("radius")}
          />
          <Button
            title="Postcode list"
            variant={mode === "postcode_list" ? "primary" : "outline"}
            onPress={() => setMode("postcode_list")}
          />
        </View>

        {mode === "radius" && (
          <FormField
            label="Radius (miles)"
            value={radius}
            onChangeText={setRadius}
            placeholder="15"
            keyboardType="number-pad"
            maxLength={3}
          />
        )}

        {mode === "postcode_list" && (
          <FormField
            label="Postcode sectors (comma separated)"
            value={sectors}
            onChangeText={setSectors}
            placeholder="e.g. SK8, M20, M22"
          />
        )}

        <Text variant="body" weight="semibold">
          Nations served
        </Text>
        <View className="flex-row flex-wrap gap-2">
          {NATIONS.map((n) => (
            <Button
              key={n.key}
              title={n.label}
              variant={nations.has(n.key) ? "primary" : "outline"}
              onPress={() => toggleNation(n.key)}
            />
          ))}
        </View>

        <Button
          title="Continue"
          onPress={() => onNext({ postcode, address, mode, radius, sectors, nations: Array.from(nations) })}
          disabled={!postcode.trim() || !address.trim()}
        />
      </View>
    </ScrollView>
  );
}
