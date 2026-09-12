/**
 * Shared design tokens for the My Trade Portal white-label iOS app.
 *
 * Base brand: hi-vis yellow (#FFC107) on deep slate ink (#0F1E26), per the
 * brand sheet palette (Slate #0F1E26, Yellow #FFC107).
 */

export const colors = {
  primary: "#0F1E26" as string, // slate ink — interactive base
  primaryDark: "#0A151B",
  accent: "#FFC107", // hi-vis yellow — brand highlights
  accentDark: "#CC8F00",
  background: "#FFFFFF",
  surface: "#F3F4F6",
  border: "#E5E7EB",
  text: "#111827",
  textSecondary: "#6B7280",
  success: "#10B981",
  warning: "#F59E0B",
  error: "#EF4444",
  accentSurface: "#FEF9E8", // brand yellow tint — hero/highlight surfaces
  accentBorder: "#FBE488",
  accentText: "#8F6600",
  infoSurface: "#F2F5F6", // light slate tint — neutral metric surfaces
  infoText: "#0F1E26",
  infoBorder: "#C3CFD5",
  successSurface: "#ECFDF5",
  successBorder: "#A7F3D0",
  successText: "#065F46",
  warningSurface: "#FFFBEB",
  warningBorder: "#FCD34D",
  warningText: "#B45309",
  errorSurface: "#FEF2F2",
  errorBorder: "#FECACA",
  errorText: "#B91C1C",
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
