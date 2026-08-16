import { Text as RNText, TextProps as RNTextProps, StyleSheet } from "react-native";
import { useTheme } from "../../theme/ThemeProvider";

type TextProps = RNTextProps & {
  variant?: "body" | "title" | "subtitle" | "caption" | "label";
  color?: "text" | "secondary" | "primary" | "success" | "warning";
  weight?: "normal" | "medium" | "semibold" | "bold";
  align?: "auto" | "left" | "right" | "center" | "justify";
};

export function Text({
  variant = "body",
  color = "text",
  weight = "normal",
  align = "left",
  style,
  ...props
}: TextProps) {
  const { colors, typography } = useTheme();

  const colorMap = {
    text: colors.text,
    secondary: colors.textSecondary,
    primary: colors.primary,
    success: colors.success,
    warning: colors.warning,
  };

  const sizeMap = {
    caption: typography.sizes.sm,
    label: typography.sizes.xs,
    body: typography.sizes.md,
    subtitle: typography.sizes.lg,
    title: typography.sizes["2xl"],
  };

  return (
    <RNText
      style={[
        {
          color: colorMap[color],
          fontSize: sizeMap[variant],
          fontFamily: typography.fontFamily,
          fontWeight: typography.weights[weight] as any,
          textAlign: align,
        },
        style,
      ]}
      {...props}
    />
  );
}
