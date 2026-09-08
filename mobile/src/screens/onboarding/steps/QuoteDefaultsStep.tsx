import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Text } from "../../../components/ui/Text";

type QuoteDefaultsStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

export function QuoteDefaultsStep({ onNext }: QuoteDefaultsStepProps) {
  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Quote defaults & terms
        </Text>
        <Text variant="body" color="secondary">
          Validity, deposits, payment terms, and T&Cs template.
        </Text>

        <View className="rounded-2xl bg-slate-100 p-4">
          <Text variant="body" weight="semibold">
            Standard defaults loaded
          </Text>
          <Text variant="caption" color="secondary">
            30-day validity, payment on completion, and a UK trades T&Cs template. Edit these in Settings later.
          </Text>
        </View>

        <Button title="Skip for now" variant="outline" onPress={() => onNext({ skipped: true })} />
      </View>
    </ScrollView>
  );
}
