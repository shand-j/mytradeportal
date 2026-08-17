import { create } from "zustand";
import { AppRole, TradeRole, User } from "../types";
import { config } from "../lib/config";
import { ApiError, NetworkError } from "../lib/apiClient";
import { loginWithToken, logoutToken } from "../api/auth";
import { useBusinessStore } from "./businessStore";

type AuthState = {
  role: AppRole;
  user: User | null;
  onboardingComplete: boolean;
  isRegistering: boolean;
  /** True while a real API login is in flight. */
  loading: boolean;
  setRole: (role: AppRole) => void;
  setUser: (user: User | null) => void;
  startRegistration: (targetRole: AppRole) => void;
  login: (email: string, password: string, role: AppRole) => Promise<boolean>;
  logout: () => void;
  completeOnboarding: () => void;
  resetDemo: () => void;
};

const DEMO_CREDENTIALS: Record<"trade" | "customer", { email: string; password: string }> = {
  trade: { email: "owner@demo.trade", password: "demo123" },
  customer: { email: "jane@example.com", password: "demo123" },
};

const TRADE_ROLES: TradeRole[] = ["owner", "admin", "office_manager", "engineer"];
const asTradeRole = (role: string): TradeRole =>
  (TRADE_ROLES as string[]).includes(role) ? (role as TradeRole) : "owner";

function demoLogin(
  email: string,
  password: string,
  targetRole: AppRole,
  set: (partial: Partial<AuthState>) => void
): boolean {
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
}

export const useAuthStore = create<AuthState>((set, get) => ({
  role: "guest",
  user: null,
  onboardingComplete: false,
  isRegistering: false,
  loading: false,

  setRole: (role) => set({ role }),

  setUser: (user) => set({ user }),

  login: async (email, password, targetRole) => {
    // Connected mode: try the real backend first for trade users. Customer auth
    // is not wired yet (Phase 3), so customers stay on the demo path.
    if (config.apiEnabled && targetRole === "trade") {
      set({ loading: true });
      try {
        const slug = useBusinessStore.getState().business?.slug ?? "demo";
        const apiUser = await loginWithToken(email, password, slug);
        set({
          user: {
            id: apiUser.id,
            email: apiUser.email,
            fullName: apiUser.fullName,
            role: asTradeRole(apiUser.role),
          },
          role: "trade",
          onboardingComplete: true,
          isRegistering: false,
          loading: false,
        });
        return true;
      } catch (err) {
        set({ loading: false });
        // Real backend rejected the credentials — do not silently fall back.
        if (err instanceof ApiError) return false;
        // NetworkError (offline / no server) — fall through to demo mode so the
        // interactive demo keeps working without a backend.
        if (!(err instanceof NetworkError)) throw err;
      }
    }

    return demoLogin(email, password, targetRole, set);
  },

  logout: () => {
    void logoutToken();
    set({ role: "guest", user: null, onboardingComplete: false, isRegistering: false });
  },

  resetDemo: () => {
    void logoutToken();
    set({ role: "guest", user: null, onboardingComplete: false, isRegistering: false });
  },

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
