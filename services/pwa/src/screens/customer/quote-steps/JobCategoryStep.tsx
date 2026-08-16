import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Icon, IconName } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";
import { ALL_CATEGORIES, StepPropsWithBusiness } from "./types";

export function JobCategoryStep({ formData, updateFormData, onNext, business }: StepPropsWithBusiness) {
  const [category, setCategory] = useState(formData.category);

  const enabledKeys = new Set(business?.businessServices ?? ALL_CATEGORIES.map((c) => c.key));
  const categories = ALL_CATEGORIES.filter((c) => enabledKeys.has(c.key));

  const handleNext = () => {
    updateFormData({ category });
    onNext();
  };

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        What do you need?
      </Text>
      <Text variant="body" color="secondary">
        Select the job type that best matches your work.
      </Text>

      <View style={styles.grid}>
        {categories.map((cat) => {
          const active = category === cat.key;
          return (
            <Button
              key={cat.key}
              testID={`quote-category-${cat.key}`}
              title={cat.label}
              variant={active ? "primary" : "outline"}
              onPress={() => setCategory(cat.key)}
            />
          );
        })}
      </View>

      <Button testID="quote-category-continue" title="Continue" onPress={handleNext} disabled={!category} />
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
