import { View } from "react-native";
import { Button } from "../ui/Button";
import { Text } from "../ui/Text";
import { ChecklistItem } from "./LaunchGateChecklist";

type PostLaunchChecklistProps = {
  items: ChecklistItem[];
  onComplete?: (key: string) => void;
};

export function PostLaunchChecklist({ items, onComplete }: PostLaunchChecklistProps) {
  return (
    <View className="gap-3 rounded-2xl bg-slate-100 p-4">
      <Text variant="body" weight="semibold">
        Post-launch checklist
      </Text>

      {items.map((item) => {
        const isComplete = item.status === "complete";
        return (
          <View key={item.key} className="flex-row items-center gap-3">
            <View className="flex-1">
              <Text variant="body">{item.label}</Text>
            </View>
            <Button
              title="Complete"
              size="sm"
              variant={isComplete ? "secondary" : "outline"}
              onPress={() => onComplete?.(item.key)}
              disabled={isComplete}
            />
          </View>
        );
      })}
    </View>
  );
}
