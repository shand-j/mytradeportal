/**
 * Shared design tokens for the My Trade Portal white-label iOS app.
 *
 * Base brand: hi-vis yellow (#F2B100) on deep slate ink (#1B2A32), per the
 * brand mark in `marketing/assets/mtp-icon-hivis-yellow-on-slate.svg`.
 */

export const colors = {
  primary: "#1B2A32" as string, // slate ink — interactive base
  primaryDark: "#0F1E26",
  accent: "#F2B100", // hi-vis yellow — brand highlights
  accentDark: "#C78F00",
  background: "#FFFFFF",
  surface: "#F3F4F6",
  border: "#E5E7EB",
  text: "#111827",
  textSecondary: "#6B7280",
  success: "#10B981",
  warning: "#F59E0B",
  error: "#EF4444",
  infoSurface: "#F2F5F6",
  infoText: "#1B2A32",
  successSurface: "#ECFDF5",
  successText: "#065F46",
  warningSurface: "#FFFBEB",
  warningBorder: "#FCD34D",
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  "2xl": 32,
  "3xl": 48,
} as const;

export const radii = {
  sm: 6,
  md: 8,
  lg: 12,
  xl: 16,
  "2xl": 20,
  full: 9999,
} as const;

export const typography = {
  fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif",
  sizes: {
    xs: 10,
    sm: 12,
    md: 14,
    lg: 16,
    xl: 18,
    "2xl": 20,
    "3xl": 22,
    "4xl": 28,
  },
  weights: {
    normal: "400",
    medium: "500",
    semibold: "600",
    bold: "700",
  },
} as const;

export type Colors = typeof colors;
export type Theme = {
  colors: Colors;
  spacing: typeof spacing;
  radii: typeof radii;
  typography: typeof typography;
};

export const theme: Theme = {
  colors,
  spacing,
  radii,
  typography,
};
