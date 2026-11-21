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
import { usePaywallStore } from "./paywallStore";

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
  sessionRestored: boolean;
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

// Root-layout remounts (notably around iOS deep-link transitions) can trigger
// session restoration more than once. Keep one in-flight restore to avoid
// repeated auth round-trips and redirect churn.
let restoreInFlight: Promise<boolean> | null = null;

export const useAuthStore = create<AuthState>((set) => ({
  role: "guest",
  user: null,
  sessionRestored: false,
  onboardingComplete: false,
  isRegistering: false,
  loading: false,

  setRole: (role) => set({ role }),

  setUser: (user) => set({ user }),

  login: async (email, password, targetRole) => {
    // A previous 402 or paywall route is session state, not a credential
    // state. Clear it before the new login so stale billing state cannot
    // redirect the first dashboard navigation.
    usePaywallStore.getState().setRequired(false);
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
          sessionRestored: true,
          onboardingComplete,
          isRegistering: false,
          loading: false,
        });
      } else {
        // Customer login is tenant-agnostic: the backend locates the account
        // by email across tenants when no slug is supplied.
        const customer = await loginCustomer(slug, email, password);
        set({
          user: { id: customer.id, email: customer.email, fullName: customer.fullName, role: "owner" },
          role: "customer",
          sessionRestored: true,
          onboardingComplete: true,
          isRegistering: false,
          loading: false,
        });
        try {
          // Tenant-agnostic login resolves the tenant server-side; load its
          // branding so customer flows that target a business (quote wizard)
          // have a slug to submit against.
          const tenant = await fetchCurrentTenant();
          useBusinessStore.getState().setBusiness(tenant);
        } catch {
          // Branding could not be loaded; customer flows still work with
          // default theming, but the quote wizard cannot submit.
        }
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
        sessionRestored: true,
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
    // The paywall flag is per-tenant session state — drop it so the "sign in
    // with a different account" flow doesn't bounce an active tenant through
    // /paywall on a stale 402 flag.
    usePaywallStore.getState().setRequired(false);
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
        sessionRestored: true,
        onboardingComplete: true,
        isRegistering: false,
        loading: false,
      });
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  restoreSession: () => {
    if (restoreInFlight) return restoreInFlight;

    usePaywallStore.getState().setRequired(false);
    set({ loading: true });
    restoreInFlight = (async () => {
      try {
        // Skip the round-trip (and a noisy 401) when no token is stored.
        const token = await tokenStorage.getToken();
        if (!token) {
          set({ loading: false, sessionRestored: true });
          return false;
        }

        try {
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
            sessionRestored: true,
            onboardingComplete,
            isRegistering: false,
            loading: false,
          });
          return true;
        } catch (err) {
          // /auth/me rejects customer (homeowner) tokens — restore those via
          // the customer portal instead of dropping the session.
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
                sessionRestored: true,
                onboardingComplete: true,
                isRegistering: false,
                loading: false,
              });
              try {
                // Restore the tenant branding so customer flows that submit
                // against a business slug (quote wizard) keep working.
                const tenant = await fetchCurrentTenant();
                useBusinessStore.getState().setBusiness(tenant);
              } catch {
                // Branding restore failed; non-fatal for the session itself.
              }
              return true;
            } catch (customerErr) {
              if (
                customerErr instanceof ApiError &&
                (customerErr.status === 401 || customerErr.status === 403)
              ) {
                await logoutToken();
              }
            }
          } else if (
            err instanceof ApiError &&
            (err.status === 401 || err.status === 403)
          ) {
            await logoutToken();
          }
        }
      } catch {
        // Network/SecureStore failures are transient; keep any stored token so
        // a later retry can restore the session.
      }
      set({ loading: false, sessionRestored: true });
      return false;
    })();

    void restoreInFlight.finally(() => {
      restoreInFlight = null;
    });
    return restoreInFlight;
  },
}));
