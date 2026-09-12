import { View } from "react-native";
import { Text } from "./Text";

/**
 * "LIVE" data indicator — slate surface with a hi-vis yellow dot, per the
 * platform brand (replaces the old green pill).
 */
export function LiveBadge({ compact = false }: { compact?: boolean }) {
  return (
    <View
      className={`flex-row items-center gap-1 rounded-full bg-primary-50 ${
        compact ? "px-1.5 py-0.5" : "px-2 py-0.5"
      }`}
    >
      <View className="h-1.5 w-1.5 rounded-full bg-accent-500" />
      <Text variant="caption" style={{ color: "#0F1E26", fontSize: 9 }}>
        LIVE
      </Text>
    </View>
  );
}
