import { ReactNode } from "react";
import { useBusinessStore } from "../stores/businessStore";
import { Theme } from "@mtp/shared-ts";
import { BusinessConfig } from "../types";

export type ThemeContextValue = {
  theme: Theme;
  business: BusinessConfig | null;
  setBusiness: (business: BusinessConfig | null) => void;
};

export function useTheme(): Theme {
  return useBusinessStore((state) => state.theme);
}

export function useBusiness(): ThemeContextValue {
  const business = useBusinessStore((state) => state.business);
  const theme = useBusinessStore((state) => state.theme);
  const setBusiness = useBusinessStore((state) => state.setBusiness);

  return { theme, business, setBusiness };
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
