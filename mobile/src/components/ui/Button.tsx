import { Pressable, PressableProps, StyleSheet, View, ViewStyle } from "react-native";
import { Text } from "./Text";
import { useTheme } from "../../theme/ThemeProvider";

type ButtonProps = PressableProps & {
  title: string;
  variant?: "primary" | "secondary" | "outline" | "ghost";
  size?: "default" | "sm";
  testID?: string;
};

export function Button({
  title,
  variant = "primary",
  size = "default",
  testID,
  disabled,
  ...props
}: ButtonProps) {
  const { colors, radii, spacing } = useTheme();

  const backgroundColor =
    variant === "primary" ? colors.primary : variant === "secondary" ? colors.surface : "transparent";
  const borderColor = variant === "outline" ? colors.border : "transparent";
  const textColor = variant === "primary" ? "#FFFFFF" : colors.text;
  const paddingHorizontal = size === "sm" ? spacing.md : spacing.lg;
  const paddingVertical = size === "sm" ? spacing.sm : spacing.md;
  const fontSize = size === "sm" ? 14 : 16;

  // Use a static style array rather than a `({ pressed }) => ...` style
  // function: NativeWind v4's JSX interop does not reliably apply function
  // styles on native, which dropped the primary background colour.
  const containerStyle: ViewStyle = {
    backgroundColor,
    borderColor,
    borderWidth: variant === "outline" ? 1 : 0,
    borderRadius: radii.lg,
    paddingHorizontal,
    paddingVertical,
    opacity: disabled ? 0.5 : 1,
  };

  return (
    <Pressable
      testID={testID}
      disabled={disabled}
      style={[styles.base, containerStyle]}
      {...props}
    >
      <View style={styles.content}>
        <Text variant="body" weight="semibold" style={{ color: textColor, fontSize }}>
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
