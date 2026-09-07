import { ReactNode } from "react";
import { useBusinessStore } from "../stores/businessStore";
import { Theme } from "@mtp/shared-ts";
import { BusinessConfig } from "../types";

export type ThemeContextValue = {
  theme: Theme;
  business: BusinessConfig | null;
  isLoading: boolean;
  error: string | null;
  setBusiness: (business: BusinessConfig | null) => void;
  loadBusiness: (slugOrCode: string) => Promise<void>;
  clearBusiness: () => void;
};

export function useTheme(): Theme {
  return useBusinessStore((state) => state.theme);
}

export function useBusiness(): ThemeContextValue {
  const business = useBusinessStore((state) => state.business);
  const theme = useBusinessStore((state) => state.theme);
  const isLoading = useBusinessStore((state) => state.isLoading);
  const error = useBusinessStore((state) => state.error);
  const setBusiness = useBusinessStore((state) => state.setBusiness);
  const loadBusiness = useBusinessStore((state) => state.loadBusiness);
  const clearBusiness = useBusinessStore((state) => state.clearBusiness);

  return { theme, business, isLoading, error, setBusiness, loadBusiness, clearBusiness };
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
