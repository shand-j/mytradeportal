import { View } from "react-native";
import { Button } from "./Button";

export type OptionChipsProps = {
  /** testID prefix; each chip appends a slug of its option label. */
  testIDPrefix: string;
  options: string[];
  /** The selected option, or "" when nothing is selected. */
  selected: string;
  onSelect: (value: string) => void;
};

const slug = (value: string) => value.toLowerCase().replace(/\+/g, "plus");

/**
 * Single-select chip group (primary/outline buttons) used wherever the user
 * picks one option from a fixed set — quote intake, customer property
 * details. The trailing "Not sure" chip clears the selection ("").
 */
export function OptionChips({ testIDPrefix, options, selected, onSelect }: OptionChipsProps) {
  return (
    <View className="flex-row flex-wrap gap-2">
      {options.map((option) => (
        <Button
          key={option}
          testID={`${testIDPrefix}-${slug(option)}`}
          title={option}
          variant={selected === option ? "primary" : "outline"}
          onPress={() => onSelect(option)}
        />
      ))}
      <Button
        testID={`${testIDPrefix}-not-sure`}
        title="Not sure"
        variant={selected === "" ? "primary" : "outline"}
        onPress={() => onSelect("")}
      />
    </View>
  );
}
