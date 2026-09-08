import { ReactNode, useEffect } from "react";
import { useAuthStore } from "../stores/authStore";
import { RegisterBusinessInput } from "../api/onboarding";
import { AppRole, User } from "../types";

export type AuthContextValue = {
  role: AppRole;
  user: User | null;
  isAuthenticated: boolean;
  onboardingComplete: boolean;
  isRegistering: boolean;
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
  loading: boolean;
};

export function useAuth(): AuthContextValue {
  const state = useAuthStore();

  return {
    role: state.role,
    user: state.user,
    isAuthenticated: state.user !== null,
    onboardingComplete: state.onboardingComplete,
    isRegistering: state.isRegistering,
    setRole: state.setRole,
    setUser: state.setUser,
    startRegistration: state.startRegistration,
    login: state.login,
    registerCustomerAccount: state.registerCustomerAccount,
    logout: state.logout,
    completeOnboarding: state.completeOnboarding,
    finishRegistration: state.finishRegistration,
    restoreSession: state.restoreSession,
    loading: state.loading,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const { restoreSession } = useAuthStore();

  useEffect(() => {
    void restoreSession();
  }, [restoreSession]);

  return <>{children}</>;
}
