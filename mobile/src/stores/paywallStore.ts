import { create } from "zustand";

/**
 * Set by the API client when the backend answers 402 subscription_required.
 * Kept in its own module (not authStore) to avoid an import cycle with
 * apiClient, which both this store and authStore flow through.
 */
type PaywallState = {
  required: boolean;
  setRequired: (required: boolean) => void;
};

export const usePaywallStore = create<PaywallState>((set) => ({
  required: false,
  setRequired: (required) => set({ required }),
}));
