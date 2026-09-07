import { create } from "zustand";
import { theme as defaultTheme, Theme } from "@mtp/shared-ts";
import { fetchPublicConfig } from "../api/businesses";
import { BusinessConfig } from "../types";

type BusinessState = {
  business: BusinessConfig | null;
  theme: Theme;
  isLoading: boolean;
  error: string | null;
  setBusiness: (business: BusinessConfig | null) => void;
  loadBusiness: (slugOrCode: string) => Promise<void>;
  clearBusiness: () => void;
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
  isLoading: false,
  error: null,

  setBusiness: (business) =>
    set({
      business,
      theme: deriveTheme(business),
      error: null,
    }),

  loadBusiness: async (slugOrCode: string) => {
    const query = slugOrCode.trim().toLowerCase();
    if (!query) {
      set({ error: "Enter a business code or slug", isLoading: false });
      return;
    }

    set({ isLoading: true, error: null });

    try {
      const live = await fetchPublicConfig(query);
      set({ business: live, theme: deriveTheme(live), isLoading: false, error: null });
    } catch {
      set({
        business: null,
        theme: defaultTheme,
        isLoading: false,
        error: "We couldn't find a business with that code. Please check and try again.",
      });
    }
  },

  clearBusiness: () =>
    set({
      business: null,
      theme: defaultTheme,
      error: null,
      isLoading: false,
    }),
}));
