import { create } from "zustand";
import { theme as defaultTheme, Theme } from "@mtp/shared-ts";
import { BusinessConfig } from "../types";

type BusinessState = {
  business: BusinessConfig | null;
  theme: Theme;
  setBusiness: (business: BusinessConfig | null) => void;
};

function deriveTheme(business: BusinessConfig | null): Theme {
  if (!business?.primaryColor) return defaultTheme;
  return {
    ...defaultTheme,
    colors: {
      ...defaultTheme.colors,
      primary: business.primaryColor,
    },
  };
}

export const useBusinessStore = create<BusinessState>((set) => ({
  business: null,
  theme: defaultTheme,

  setBusiness: (business) =>
    set({
      business,
      theme: deriveTheme(business),
    }),
}));
