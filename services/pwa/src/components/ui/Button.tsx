import { Pressable, PressableProps, StyleSheet, View } from "react-native";
import { Text } from "./Text";
import { useTheme } from "../../theme/ThemeProvider";

type ButtonProps = PressableProps & {
  title: string;
  variant?: "primary" | "secondary" | "outline" | "ghost";
  size?: "default" | "sm";
  testID?: string;
};

export function Button({ title, variant = "primary", size = "default", testID, ...props }: ButtonProps) {
  const { colors, radii, spacing } = useTheme();

  const backgroundColor =
    variant === "primary" ? colors.primary : variant === "secondary" ? colors.surface : "transparent";
  const borderColor = variant === "outline" ? colors.border : "transparent";
  const textColor = variant === "primary" ? "#FFFFFF" : colors.text;
  const paddingHorizontal = size === "sm" ? spacing.md : spacing.lg;
  const paddingVertical = size === "sm" ? spacing.sm : spacing.md;
  const fontSize = size === "sm" ? 14 : 16;

  return (
    <Pressable
      testID={testID}
      style={({ pressed }) => ({
        ...styles.base,
        backgroundColor,
        borderColor,
        borderWidth: variant === "outline" ? 1 : 0,
        borderRadius: radii.lg,
        paddingHorizontal,
        paddingVertical,
        opacity: pressed || props.disabled ? 0.7 : 1,
      })}
      {...props}
    >
      <View style={styles.content}>
        <Text
          variant="body"
          weight="semibold"
          style={{ color: textColor, fontSize }}
        >
          {title}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: "center",
    justifyContent: "center",
  },
  content: {
    flexDirection: "row",
    alignItems: "center",
  },
});
