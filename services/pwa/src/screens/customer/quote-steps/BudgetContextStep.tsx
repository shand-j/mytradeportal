import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Text } from "../../../components/ui/Text";
import { StepPropsWithBusiness } from "./types";

const BUDGET_BANDS = [
  { key: "under_250", label: "Under £250" },
  { key: "250_500", label: "£250–£500" },
  { key: "500_1k", label: "£500–£1,000" },
  { key: "1k_2.5k", label: "£1,000–£2,500" },
  { key: "2.5k_plus", label: "£2,500+" },
  { key: "no_idea", label: "No idea" },
];

const SOURCES = [
  { key: "google", label: "Google" },
  { key: "facebook", label: "Facebook" },
  { key: "recommendation", label: "Recommendation" },
  { key: "van_sticker", label: "Van sticker" },
  { key: "flyer", label: "Flyer" },
  { key: "other", label: "Other" },
];

export function BudgetContextStep({ formData, updateFormData, onNext }: StepPropsWithBusiness) {
  const [data, setData] = useState(formData.budgetContext);

  const update = (key: string, value: any) => {
    setData((prev) => ({ ...prev, [key]: value }));
  };

  const handleNext = () => {
    updateFormData({ budgetContext: data });
    onNext();
  };

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        Budget & context
      </Text>
      <Text variant="body" color="secondary">
        This helps us match the right solution to your budget.
      </Text>

      <Text variant="body" weight="semibold">
        Budget band (optional)
      </Text>
      <View style={styles.options}>
        {BUDGET_BANDS.map((band) => (
          <Button
            key={band.key}
            title={band.label}
            variant={data.budgetBand === band.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("budgetBand", band.key)}
          />
        ))}
      </View>

      <Text variant="body" weight="semibold">
        How did you hear about us? (optional)
      </Text>
      <View style={styles.options}>
        {SOURCES.map((source) => (
          <Button
            key={source.key}
            title={source.label}
            variant={data.howDidYouHear === source.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("howDidYouHear", source.key)}
          />
        ))}
      </View>

      <Text variant="body" weight="semibold">
        Insurance claim?
      </Text>
      <View style={styles.options}>
        <Button
          title="Yes"
          variant={data.insuranceClaim === true ? "primary" : "outline"}
          size="sm"
          onPress={() => update("insuranceClaim", true)}
        />
        <Button
          title="No"
          variant={data.insuranceClaim === false ? "primary" : "outline"}
          size="sm"
          onPress={() => update("insuranceClaim", false)}
        />
      </View>

      <Button testID="quote-budget-continue" title="Continue" onPress={handleNext} />
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
});
