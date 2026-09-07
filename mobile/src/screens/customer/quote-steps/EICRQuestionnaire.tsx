import { useState } from "react";
import { StyleSheet, TextInput, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";
import { StepPropsWithBusiness } from "./types";

const WHO_ASKING = [
  { key: "landlord", label: "Landlord" },
  { key: "homeowner", label: "Homeowner" },
  { key: "buyer", label: "Buyer" },
  { key: "seller", label: "Seller" },
];

const OCCUPANCY = [
  { key: "vacant", label: "Vacant" },
  { key: "tenanted", label: "Tenanted" },
  { key: "owner_occupied", label: "Owner-occupied" },
];

const REMEDIAL = [
  { key: "yes", label: "Yes, include in quote" },
  { key: "separate", label: "Quote separately" },
  { key: "no", label: "No remedial work" },
];

export function EICRQuestionnaire({ formData, updateFormData, onNext }: StepPropsWithBusiness) {
  const [data, setData] = useState<Record<string, any>>(formData.questionnaire.eicr ?? {});
  const [notes, setNotes] = useState((formData.questionnaire.notes as string) ?? "");

  const update = (key: string, value: any) => {
    setData((prev) => ({ ...prev, [key]: value }));
  };

  const handleNext = () => {
    updateFormData({
      questionnaire: { ...formData.questionnaire, eicr: data, notes },
    });
    onNext();
  };

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        EICR (Electrical Installation Condition Report)
      </Text>
      <Text variant="body" color="secondary">
        Who is the report for and how should we access the property?
      </Text>

      <Text variant="body" weight="semibold">
        Who is asking?
      </Text>
      <View style={styles.options}>
        {WHO_ASKING.map((who) => (
          <Button
            key={who.key}
            title={who.label}
            variant={data.who === who.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("who", who.key)}
          />
        ))}
      </View>

      <FormField
        label="Last EICR date (if known)"
        value={data.last_eicr ?? ""}
        onChangeText={(text) => update("last_eicr", text)}
        placeholder="MM/YYYY or leave blank"
      />

      <Text variant="body" weight="semibold">
        Property occupancy
      </Text>
      <View style={styles.options}>
        {OCCUPANCY.map((occ) => (
          <Button
            key={occ.key}
            title={occ.label}
            variant={data.occupancy === occ.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("occupancy", occ.key)}
          />
        ))}
      </View>

      <FormField
        label="Number of circuits (or best guess)"
        value={data.circuits ?? ""}
        onChangeText={(text) => update("circuits", text)}
        placeholder="e.g. 8"
        keyboardType="number-pad"
        helper="More circuits mean a longer inspection and report."
      />

      <Text variant="body" weight="semibold">
        Remedial works in quote?
      </Text>
      <View style={styles.options}>
        {REMEDIAL.map((opt) => (
          <Button
            key={opt.key}
            title={opt.label}
            variant={data.remedial === opt.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("remedial", opt.key)}
          />
        ))}
      </View>

      <TextInput
        style={styles.notesInput}
        placeholder="Anything else we should know?"
        value={notes}
        onChangeText={setNotes}
        multiline
        numberOfLines={3}
      />

      <Button testID="quote-eicr-continue" title="Continue" onPress={handleNext} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
  },
  options: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  notesInput: {
    height: 80,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    backgroundColor: "#FFFFFF",
    padding: 12,
    fontSize: 14,
    textAlignVertical: "top",
  },
});
