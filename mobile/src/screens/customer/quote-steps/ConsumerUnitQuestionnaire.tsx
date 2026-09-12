import { useState } from "react";
import { StyleSheet, TextInput, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";
import { StepPropsWithBusiness } from "./types";

const UPGRADE_REASONS = [
  { key: "old_fuse_wire", label: "Old fuse wire" },
  { key: "no_rcd", label: "No RCD protection" },
  { key: "adding_circuits", label: "Adding circuits" },
  { key: "survey_recommendation", label: "Survey recommendation" },
  { key: "other", label: "Other" },
];

const KNOWN_FAULTS = [
  { key: "burning_smell", label: "Burning smell", redFlag: true },
  { key: "shocks", label: "Electric shocks", redFlag: true },
  { key: "water", label: "Water on electrics", redFlag: true },
  { key: "repeated_tripping", label: "Repeated tripping", redFlag: false },
  { key: "partial_power_loss", label: "Partial power loss", redFlag: false },
  { key: "none", label: "None", redFlag: false },
];

export function ConsumerUnitQuestionnaire({ formData, updateFormData, onNext }: StepPropsWithBusiness) {
  const [data, setData] = useState<Record<string, any>>(formData.questionnaire.consumer_unit ?? {});
  const [notes, setNotes] = useState((formData.questionnaire.notes as string) ?? "");

  const update = (key: string, value: any) => {
    setData((prev) => ({ ...prev, [key]: value }));
  };

  const toggleFault = (key: string) => {
    setData((prev) => {
      const faults = new Set(prev.known_faults ?? []);
      if (faults.has(key)) faults.delete(key);
      else faults.add(key);
      return { ...prev, known_faults: Array.from(faults) };
    });
  };

  const handleNext = () => {
    const knownFaults = (data.known_faults as string[]) ?? [];
    const redFlags = knownFaults.filter((f) => KNOWN_FAULTS.find((k) => k.key === f)?.redFlag);
    const symptoms = new Set([...formData.redFlagSymptoms, ...redFlags]);
    updateFormData({
      questionnaire: { ...formData.questionnaire, consumer_unit: data, notes },
      redFlagSymptoms: Array.from(symptoms),
    });
    onNext();
  };

  const circuits = data.circuits ? parseInt(data.circuits, 10) : 0;
  const completeness = Math.min(100, 30 + circuits * 4 + (data.reason ? 20 : 0));

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        Consumer unit upgrade
      </Text>
      <Text variant="body" color="secondary">
        A few details help us estimate the right replacement unit.
      </Text>

      <FormField
        label="Number of circuits"
        value={data.circuits ?? ""}
        onChangeText={(text) => update("circuits", text.replace(/[^0-9]/g, ""))}
        placeholder="Count the switches on your consumer unit"
        keyboardType="number-pad"
        helper="Tip: you'll add a photo of your consumer unit on the next step — counting the switches now helps us size the replacement"
        testID="quote-cu-circuits"
      />

      <Text variant="body" weight="semibold">
        Reason for upgrade
      </Text>
      <View style={styles.options}>
        {UPGRADE_REASONS.map((reason) => (
          <Button
            key={reason.key}
            title={reason.label}
            variant={data.reason === reason.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("reason", reason.key)}
          />
        ))}
      </View>

      <Text variant="body" weight="semibold">
        Known faults
      </Text>
      <View style={styles.options}>
        {KNOWN_FAULTS.map((fault) => (
          <Button
            key={fault.key}
            title={fault.label}
            variant={((data.known_faults as string[]) ?? []).includes(fault.key) ? "primary" : "outline"}
            size="sm"
            onPress={() => toggleFault(fault.key)}
          />
        ))}
      </View>

      <Text variant="body" weight="semibold">
        Property occupied during work?
      </Text>
      <View style={styles.options}>
        <Button
          title="Yes"
          variant={data.occupied === true ? "primary" : "outline"}
          size="sm"
          onPress={() => update("occupied", true)}
        />
        <Button
          title="No"
          variant={data.occupied === false ? "primary" : "outline"}
          size="sm"
          onPress={() => update("occupied", false)}
        />
      </View>
      {data.occupied === true ? (
        <Text variant="caption" color="secondary">
          We’ll plan power-down windows around you.
        </Text>
      ) : null}

      <Text variant="body" weight="semibold">
        Detail completeness
      </Text>
      <View style={styles.completenessBar}>
        <View style={[styles.completenessFill, { width: `${completeness}%` }]} />
      </View>
      <Text variant="caption" color="secondary">
        {completeness}% — more detail helps your electrician prepare an accurate quote.
      </Text>

      <TextInput
        style={styles.notesInput}
        placeholder="Anything else we should know?"
        value={notes}
        onChangeText={setNotes}
        multiline
        numberOfLines={3}
      />

      <Button testID="quote-consumer-unit-continue" title="Continue" onPress={handleNext} />
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
  completenessBar: {
    height: 8,
    borderRadius: 4,
    backgroundColor: "#E5E7EB",
  },
  completenessFill: {
    height: 8,
    borderRadius: 4,
    backgroundColor: "#0F1E26",
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
