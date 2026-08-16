import { StyleSheet, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";
import { useBusiness } from "../../../theme/ThemeProvider";
import { ALL_CATEGORIES, StepPropsWithBusiness } from "./types";

const URGENCY_LABELS: Record<string, string> = {
  emergency_today: "Emergency - today",
  this_week: "This week",
  this_month: "This month",
  flexible: "Flexible",
  just_researching: "Just researching",
};

export function ConfirmationStep({ formData, onDone }: StepPropsWithBusiness & { onDone: () => void }) {
  const { business } = useBusiness();
  const businessName = business?.name ?? "Your electrician";
  const slaHours = 24;
  const categoryLabel =
    ALL_CATEGORIES.find((c) => c.key === formData.category)?.label ?? formData.category;
  const highConfidence =
    formData.media.length > 0 &&
    formData.category !== "other" &&
    formData.triage !== "emergency";

  return (
    <View style={styles.container}>
      <View style={styles.iconCircle}>
        <Icon name="checkmark" size={40} color="#2563EB" />
      </View>

      <Text variant="title" weight="bold" align="center">
        {businessName} has your request
      </Text>
      <Text variant="body" color="secondary" align="center">
        {businessName} will review your details and send your quote — usually within {slaHours} hours.
      </Text>

      {highConfidence ? (
        <View style={styles.confidenceBanner}>
          <Icon name="checkmark" size={18} color="#065F46" />
          <Text variant="body" color="success">
            Good news — your quote is already being prepared.
          </Text>
        </View>
      ) : null}

      <View style={styles.summary}>
        <Text variant="body" weight="semibold">
          Summary
        </Text>
        <View style={styles.summaryRow}>
          <Text variant="caption" color="secondary">
            Postcode
          </Text>
          <Text variant="caption">{formData.postcode}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text variant="caption" color="secondary">
            Category
          </Text>
          <Text variant="caption">{categoryLabel}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text variant="caption" color="secondary">
            Urgency
          </Text>
          <Text variant="caption">{URGENCY_LABELS[formData.urgency] ?? formData.urgency}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text variant="caption" color="secondary">
            Photos / videos
          </Text>
          <Text variant="caption">{formData.media.length}</Text>
        </View>
      </View>

      <Button testID="quote-done" title="Done" onPress={onDone} />
      <Button
        testID="quote-create-account"
        title="Create an account to track this quote"
        variant="outline"
        onPress={onDone}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
    alignItems: "center",
  },
  iconCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: "#EFF6FF",
    alignItems: "center",
    justifyContent: "center",
    alignSelf: "center",
  },
  confidenceBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    padding: 12,
    borderRadius: 12,
    backgroundColor: "#ECFDF5",
    alignSelf: "stretch",
  },
  summary: {
    alignSelf: "stretch",
    gap: 8,
    padding: 16,
    borderRadius: 16,
    backgroundColor: "#F3F4F6",
  },
  summaryRow: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
});
