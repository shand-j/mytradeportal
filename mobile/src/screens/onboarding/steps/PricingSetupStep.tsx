import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Text } from "../../../components/ui/Text";

type PricingSetupStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

export function PricingSetupStep({ onNext }: PricingSetupStepProps) {
  return (
    <ScrollView className="flex-1">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Pricing setup
        </Text>
        <Text variant="body" color="secondary">
          Set labour models, day rates, call-out fees, and materials markup per category.
        </Text>

        <View className="rounded-2xl bg-slate-100 p-4">
          <Text variant="body" weight="semibold">
            Default rates
          </Text>
          <Text variant="caption" color="secondary">
            Default labour and material rates will be loaded. You can refine them in the dashboard later.
          </Text>
        </View>

        <Button title="Skip for now" variant="outline" onPress={() => onNext({ skipped: true })} />
      </View>
    </ScrollView>
  );
}
