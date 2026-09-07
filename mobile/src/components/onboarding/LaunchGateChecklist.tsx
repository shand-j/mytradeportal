import { View } from "react-native";
import { Icon } from "../ui/Icon";
import { Text } from "../ui/Text";

export type ChecklistStatus = "complete" | "skipped" | "pending";

export type ChecklistItem = {
  key: string;
  label: string;
  status: ChecklistStatus;
};

export function LaunchGateChecklist({ items }: { items: ChecklistItem[] }) {
  return (
    <View className="gap-3 rounded-2xl bg-slate-100 p-4">
      {items.map((item) => {
        const isComplete = item.status === "complete";
        const isSkipped = item.status === "skipped";
        const iconName = isComplete ? "checkmark" : isSkipped ? "info" : "more";
        const iconColor = isComplete ? "#10B981" : isSkipped ? "#F59E0B" : "#6B7280";
        const statusLabel = isComplete ? "Done" : isSkipped ? "Later" : "To do";

        return (
          <View key={item.key} className="flex-row items-center gap-3">
            <Icon name={iconName} size={18} color={iconColor} />
            <Text variant="body" style={{ flex: 1 }}>
              {item.label}
            </Text>
            <Text variant="caption" color="secondary">
              {statusLabel}
            </Text>
          </View>
        );
      })}
    </View>
  );
}
