import { Pressable, View } from "react-native";
import { Text } from "./Text";

export type SelectableChipProps = {
  testID?: string;
  label: string;
  selected: boolean;
  onPress: () => void;
};

/**
 * Pill toggle chip for single/multi-select settings. Selected state fills with
 * the (dark) brand primary, so the label switches to light text — dark-on-dark
 * selected chips were unreadable (beta N16/N22).
 */
export function SelectableChip({ testID, label, selected, onPress }: SelectableChipProps) {
  return (
    <Pressable testID={testID} onPress={onPress}>
      <View
        className={`rounded-full px-4 py-2 border ${
          selected ? "bg-primary border-primary" : "bg-white border-slate-200"
        }`}
      >
        <Text
          variant="body"
          weight={selected ? "semibold" : "normal"}
          style={selected ? { color: "#FFFFFF" } : undefined}
        >
          {label}
        </Text>
      </View>
    </Pressable>
  );
}
