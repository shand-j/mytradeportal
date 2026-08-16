import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Text } from "../../../components/ui/Text";

type ServicesStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

const CATEGORIES = [
  { key: "ev_charger", label: "EV charger" },
  { key: "consumer_unit", label: "Consumer unit" },
  { key: "full_rewire", label: "Full rewire" },
  { key: "partial_rewire", label: "Partial rewire" },
  { key: "eicr", label: "EICR" },
  { key: "additional_points", label: "Additional points" },
  { key: "outdoor_power", label: "Outdoor power" },
  { key: "fault_finding", label: "Fault finding" },
  { key: "smart_home", label: "Smart home" },
  { key: "lighting_design", label: "Lighting design" },
  { key: "data_networking", label: "Data networking" },
  { key: "emergency_callout", label: "Emergency callout" },
];

export function ServicesStep({ onNext }: ServicesStepProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        Services offered
      </Text>
      <Text variant="body" color="secondary">
        Choose the jobs you want to quote for. These appear in the customer form.
      </Text>

      <View style={styles.grid}>
        {CATEGORIES.map((cat) => {
          const active = selected.has(cat.key);
          return (
            <Button
              key={cat.key}
              title={cat.label}
              variant={active ? "primary" : "outline"}
              onPress={() => toggle(cat.key)}
            />
          );
        })}
      </View>

      <Button
        title="Continue"
        onPress={() => onNext({ services: Array.from(selected) })}
        disabled={selected.size === 0}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
});
