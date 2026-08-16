import { create } from "zustand";
import { AppRole, User } from "../types";

type AuthState = {
  role: AppRole;
  user: User | null;
  onboardingComplete: boolean;
  isRegistering: boolean;
  setRole: (role: AppRole) => void;
  setUser: (user: User | null) => void;
  startRegistration: (targetRole: AppRole) => void;
  login: (email: string, password: string, role: AppRole) => boolean;
  logout: () => void;
  completeOnboarding: () => void;
  resetDemo: () => void;
};

const DEMO_CREDENTIALS: Record<"trade" | "customer", { email: string; password: string }> = {
  trade: { email: "owner@demo.trade", password: "demo123" },
  customer: { email: "jane@example.com", password: "demo123" },
};

export const useAuthStore = create<AuthState>((set, get) => ({
  role: "guest",
  user: null,
  onboardingComplete: false,
  isRegistering: false,

  setRole: (role) => set({ role }),

  setUser: (user) => set({ user }),

  login: (email, password, targetRole) => {
    if (
      targetRole === "trade" &&
      email === DEMO_CREDENTIALS.trade.email &&
      password === DEMO_CREDENTIALS.trade.password
    ) {
      set({
        user: { id: "demo-owner", email, fullName: "Demo Owner", role: "owner" },
        role: "trade",
        onboardingComplete: true,
        isRegistering: false,
      });
      return true;
    }
    if (
      targetRole === "customer" &&
      email === DEMO_CREDENTIALS.customer.email &&
      password === DEMO_CREDENTIALS.customer.password
    ) {
      set({
        user: { id: "demo-customer", email, fullName: "Jane Homeowner", role: "owner" },
        role: "customer",
        onboardingComplete: true,
        isRegistering: false,
      });
      return true;
    }
    return false;
  },

  logout: () =>
    set({ role: "guest", user: null, onboardingComplete: false, isRegistering: false }),

  resetDemo: () =>
    set({ role: "guest", user: null, onboardingComplete: false, isRegistering: false }),

  startRegistration: (targetRole) =>
    set({ role: targetRole, isRegistering: true, user: null, onboardingComplete: false }),

  completeOnboarding: () => {
    const { role, user } = get();
    set({ onboardingComplete: true, isRegistering: false });
    if (role === "trade" && !user) {
      set({
        user: {
          id: "demo-owner",
          email: "owner@demo.trade",
          fullName: "Demo Owner",
          role: "owner",
        },
      });
    }
  },
}));
