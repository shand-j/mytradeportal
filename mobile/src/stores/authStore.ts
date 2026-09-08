import { create } from "zustand";
import { AppRole, TradeRole, User } from "../types";
import {
  loginWithToken,
  logoutToken,
  loginCustomer,
  registerCustomer,
  fetchMe,
  fetchCustomerMe,
  ApiUser,
} from "../api/auth";
import { fetchCurrentTenant } from "../api/businesses";
import {
  registerBusiness,
  RegisterBusinessInput,
  getOnboardingStatus,
} from "../api/onboarding";
import { ApiError, NetworkError } from "../lib/apiClient";
import { tokenStorage } from "../lib/tokenStorage";
import { useBusinessStore } from "./businessStore";

/** A tenant is fully onboarded once the backend marks it active (launched). */
async function fetchOnboardingComplete(): Promise<boolean> {
  try {
    const status = await getOnboardingStatus();
    return status.status === "active";
  } catch {
    // Status fetch failed (offline, pre-tenant) — don't trap the user in the
    // wizard on a transient error.
    return true;
  }
}

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
  registerCustomerAccount: (input: {
    fullName: string;
    email: string;
    phone: string;
    password: string;
    address?: string;
    postcode?: string;
    preferredContactMethod?: string;
    marketingConsent?: boolean;
    quoteRequestId?: string;
  }) => Promise<boolean>;
  logout: () => void;
  completeOnboarding: () => void;
  finishRegistration: (input: RegisterBusinessInput | null) => Promise<void>;
  restoreSession: () => Promise<boolean>;
};

const TRADE_ROLES: TradeRole[] = ["owner", "admin", "office_manager", "engineer"];
const asTradeRole = (role: string): TradeRole =>
  (TRADE_ROLES as string[]).includes(role) ? (role as TradeRole) : "owner";

const mapApiUser = (apiUser: ApiUser): User => ({
  id: apiUser.id,
  email: apiUser.email,
  fullName: apiUser.fullName,
  role: asTradeRole(apiUser.role),
});

export const useAuthStore = create<AuthState>((set) => ({
  role: "guest",
  user: null,
  onboardingComplete: false,
  isRegistering: false,
  loading: false,

  setRole: (role) => set({ role }),

  setUser: (user) => set({ user }),

  login: async (email, password, targetRole) => {
    set({ loading: true });
    try {
      const slug = useBusinessStore.getState().business?.slug;
      if (targetRole === "trade") {
        const { user: apiUser, tenantSlug } = await loginWithToken(email, password, slug);
        try {
          const tenant = await fetchCurrentTenant();
          useBusinessStore.getState().setBusiness(tenant);
        } catch {
          // Login succeeded but tenant branding could not be loaded; the user
          // can still use the app with default theming.
        }
        const onboardingComplete = await fetchOnboardingComplete();
        set({
          user: mapApiUser(apiUser),
          role: "trade",
          onboardingComplete,
          isRegistering: false,
          loading: false,
        });
      } else {
        if (!slug) {
          set({ loading: false });
          return false;
        }
        const customer = await loginCustomer(slug, email, password);
        set({
          user: { id: customer.id, email: customer.email, fullName: customer.fullName, role: "owner" },
          role: "customer",
          onboardingComplete: true,
          isRegistering: false,
          loading: false,
        });
      }
      return true;
    } catch (err) {
      set({ loading: false });
      // Let callers distinguish "server unreachable" from bad credentials
      // (the latter surface as `false` so the screen can show a 401 message).
      if (err instanceof NetworkError) throw err;
      return false;
    }
  },

  registerCustomerAccount: async (input) => {
    set({ loading: true });
    try {
      const slug = useBusinessStore.getState().business?.slug ?? "";
      if (!slug) {
        set({ loading: false });
        return false;
      }
      const customer = await registerCustomer(slug, input);
      set({
        user: {
          id: customer.id,
          email: customer.email,
          fullName: customer.fullName,
          role: "owner",
        },
        role: "customer",
        onboardingComplete: true,
        isRegistering: false,
        loading: false,
      });
      return true;
    } catch (err) {
      set({ loading: false });
      if (err instanceof NetworkError) throw err;
      // ApiError carries the server's detail (e.g. 409 email-already-exists);
      // let the screen show it instead of a generic failure.
      if (err instanceof ApiError) throw err;
      return false;
    }
  },

  logout: () => {
    void logoutToken();
    set({ role: "guest", user: null, onboardingComplete: false, isRegistering: false });
  },

  startRegistration: (targetRole) =>
    set({ role: targetRole, isRegistering: true, user: null, onboardingComplete: false }),

  completeOnboarding: () => {
    set({ onboardingComplete: true, isRegistering: false });
  },

  finishRegistration: async (input) => {
    if (!input) {
      throw new Error("Business details are required to create an account.");
    }

    set({ loading: true });
    try {
      const apiUser = await registerBusiness(input);
      try {
        const tenant = await fetchCurrentTenant();
        useBusinessStore.getState().setBusiness(tenant);
      } catch {
        // Provisioning succeeded but tenant branding could not be loaded.
      }
      set({
        user: mapApiUser(apiUser),
        role: "trade",
        onboardingComplete: true,
        isRegistering: false,
        loading: false,
      });
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  restoreSession: async () => {
    set({ loading: true });
    try {
      // Skip the round-trip (and a noisy 401) when no token is stored.
      const token = await tokenStorage.getToken();
      if (!token) {
        set({ loading: false });
        return false;
      }
      const apiUser = await fetchMe();
      try {
        const tenant = await fetchCurrentTenant();
        useBusinessStore.getState().setBusiness(tenant);
      } catch {
        // Session restored but tenant branding could not be loaded.
      }
      const onboardingComplete = await fetchOnboardingComplete();
      set({
        user: mapApiUser(apiUser),
        role: "trade",
        onboardingComplete,
        isRegistering: false,
        loading: false,
      });
      return true;
    } catch (err) {
      // /auth/me rejects customer (homeowner) tokens — restore those via the
      // customer portal instead of dropping the session.
      if (err instanceof ApiError && err.status === 401) {
        try {
          const customer = await fetchCustomerMe();
          set({
            user: {
              id: customer.id,
              email: customer.email,
              fullName: customer.fullName,
              role: "owner",
            },
            role: "customer",
            onboardingComplete: true,
            isRegistering: false,
            loading: false,
          });
          return true;
        } catch {
          // fall through to signed-out state
        }
      }
      set({ loading: false });
      return false;
    }
  },
}));
