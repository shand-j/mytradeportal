import { Pressable, PressableProps, StyleSheet, View } from "react-native";
import { Icon, IconName } from "./Icon";

export function IconButton({
  icon,
  size = 24,
  color = "#374151",
  onPress,
  testID,
  accessibilityLabel,
}: {
  icon: IconName;
  size?: number;
  color?: string;
  onPress: PressableProps["onPress"];
  testID?: string;
  accessibilityLabel?: string;
}) {
  return (
    <Pressable
      testID={testID}
      accessibilityLabel={accessibilityLabel}
      onPress={onPress}
      style={({ pressed }) => [styles.button, pressed && styles.pressed]}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <View style={styles.content}>
        <Icon name={icon} size={size} color={color} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    padding: 8,
    borderRadius: 10,
  },
  pressed: {
    opacity: 0.6,
    backgroundColor: "#F3F4F6",
  },
  content: {
    alignItems: "center",
    justifyContent: "center",
  },
});
