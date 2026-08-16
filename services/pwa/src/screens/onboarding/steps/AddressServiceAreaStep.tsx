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

const MOCK_ADDRESSES = [
  "123 Test Road, Stockport, SK8 3NJ",
  "124 Test Road, Stockport, SK8 3NJ",
  "125 Test Road, Stockport, SK8 3NJ",
];

export function AddressServiceAreaStep({ data, onNext }: AddressServiceAreaStepProps) {
  const [postcode, setPostcode] = useState((data?.postcode as string) ?? "SK8 3NJ");
  const [address, setAddress] = useState((data?.address as string) ?? MOCK_ADDRESSES[0]);
  const [showAddressPicker, setShowAddressPicker] = useState(false);
  const [mode, setMode] = useState<"radius" | "postcode_list">((data?.mode as "radius" | "postcode_list") ?? "radius");
  const [radius, setRadius] = useState((data?.radius as string) ?? "15");
  const [nations, setNations] = useState<Set<string>>(new Set((data?.nations as string[]) ?? ["england", "wales"]));

  const toggleNation = (key: string) => {
    setNations((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleLookup = () => {
    setShowAddressPicker(true);
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

        <Button
          title="Find address"
          variant="outline"
          onPress={handleLookup}
          disabled={postcode.length < 5}
        />

        {showAddressPicker && (
          <View className="gap-2 rounded-2xl bg-slate-50 p-3">
            <Text variant="body" weight="semibold">
              Select an address
            </Text>
            {MOCK_ADDRESSES.map((addr) => (
              <Pressable
                key={addr}
                onPress={() => {
                  setAddress(addr);
                  setShowAddressPicker(false);
                }}
                className={`rounded-xl p-3 ${address === addr ? "bg-blue-100" : "bg-white"}`}
              >
                <Text variant="body">{addr}</Text>
              </Pressable>
            ))}
          </View>
        )}

        <FormField
          label="Selected address"
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
            value="SK8, M20, M22"
            onChangeText={() => {}}
            placeholder="e.g. SK8, M20, M22"
            helper="Mock only — type any sectors."
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
          onPress={() => onNext({ postcode, address, mode, radius, nations: Array.from(nations) })}
        />
      </View>
    </ScrollView>
  );
}
