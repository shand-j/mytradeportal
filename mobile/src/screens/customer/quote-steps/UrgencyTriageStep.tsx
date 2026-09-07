import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";
import { RED_FLAG_EMERGENCY, StepPropsWithBusiness } from "./types";

const URGENCY_OPTIONS = [
  { key: "emergency_today", label: "Emergency - today", redFlag: true },
  { key: "this_week", label: "This week" },
  { key: "this_month", label: "This month" },
  { key: "flexible", label: "Flexible" },
  { key: "just_researching", label: "Just researching" },
];

export function UrgencyTriageStep({ formData, updateFormData, onNext }: StepPropsWithBusiness) {
  const [urgency, setUrgency] = useState(formData.urgency);
  const [preferredDates, setPreferredDates] = useState<string[]>(formData.preferredDates);

  const hasRedFlagSymptoms = formData.redFlagSymptoms.some((s) => RED_FLAG_EMERGENCY.includes(s));
  const isEmergencyUrgency = urgency === "emergency_today";

  const toggleDate = (date: string) => {
    setPreferredDates((prev) =>
      prev.includes(date) ? prev.filter((d) => d !== date) : [...prev, date]
    );
  };

  const handleNext = () => {
    updateFormData({ urgency, preferredDates });
    onNext();
  };

  // Generate next 14 dates as simple labels
  const dates = Array.from({ length: 14 }).map((_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i + 1);
    return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  });

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        When do you need it?
      </Text>

      <Text variant="body" weight="semibold">
        Urgency
      </Text>
      <View style={styles.options}>
        {URGENCY_OPTIONS.map((option) => (
          <Button
            key={option.key}
            title={option.label}
            variant={urgency === option.key ? "primary" : "outline"}
            size="sm"
            onPress={() => setUrgency(option.key)}
          />
        ))}
      </View>

      {hasRedFlagSymptoms || isEmergencyUrgency ? (
        <View style={styles.warning}>
          <Icon name="warning" size={20} color="#EF4444" />
          <Text variant="caption" color="warning">
            {hasRedFlagSymptoms
              ? "You’ve reported a possible electrical emergency. We’ll show you the safety callback screen next."
              : "Emergency requests are routed to the on-call electrician for a callback today."}
          </Text>
        </View>
      ) : null}

      {!isEmergencyUrgency ? (
        <>
          <Text variant="body" weight="semibold">
            Preferred dates (optional)
          </Text>
          <View style={styles.dateGrid}>
            {dates.map((date) => (
              <Button
                key={date}
                title={date}
                variant={preferredDates.includes(date) ? "primary" : "outline"}
                size="sm"
                onPress={() => toggleDate(date)}
              />
            ))}
          </View>
        </>
      ) : null}

      <Button testID="quote-urgency-continue" title="Continue" onPress={handleNext} />
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
  warning: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    padding: 12,
    borderRadius: 12,
    backgroundColor: "#FEF2F2",
    borderWidth: 1,
    borderColor: "#FECACA",
  },
  dateGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
});
