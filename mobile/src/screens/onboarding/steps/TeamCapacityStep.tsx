import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Text } from "../../../components/ui/Text";

type TeamCapacityStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

export function TeamCapacityStep({ onNext }: TeamCapacityStepProps) {
  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Team & capacity
        </Text>
        <Text variant="body" color="secondary">
          Add engineers, vans, and grades. You can skip this and set it up from the dashboard later.
        </Text>

        <View className="rounded-2xl bg-slate-100 p-4">
          <Text variant="body" weight="semibold">
            Coming soon in dashboard
          </Text>
          <Text variant="caption" color="secondary">
            Engineer invites, van tracking, and job assignment will be configured post-launch.
          </Text>
        </View>

        <Button title="Skip for now" variant="outline" onPress={() => onNext({ skipped: true })} />
      </View>
    </ScrollView>
  );
}
