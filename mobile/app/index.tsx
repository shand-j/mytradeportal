import { useEffect } from "react";
import { useRouter } from "expo-router";
import { EntryScreen } from "../src/screens/entry/EntryScreen";
import { useAuth } from "../src/contexts/AuthContext";
import { useBusinessStore } from "../src/stores/businessStore";
import { usePaywallStore } from "../src/stores/paywallStore";
import { config } from "../src/lib/config";

export default function Index() {
  const { isAuthenticated, role, onboardingComplete, isRegistering } = useAuth();
  const paywallRequired = usePaywallStore((s) => s.required);
  const router = useRouter();
  const business = useBusinessStore((state) => state.business);
  const loadBusiness = useBusinessStore((state) => state.loadBusiness);

  // White-label bootstrap: a per-tenant build targets one business slug. When
  // connected, fetch its public config once and theme the app for that tenant.
  useEffect(() => {
    if (config.businessSlug && !business) {
      void loadBusiness(config.businessSlug);
    }
  }, [business, loadBusiness]);

  useEffect(() => {
    // Registration sets isRegistering before a user exists, so route into the
    // onboarding wizard on that alone.
    if (role === "trade" && isRegistering) {
      router.replace("/onboarding");
      return;
    }
    if (isAuthenticated && role !== "guest") {
      if (role === "trade" && paywallRequired) {
        router.replace("/paywall");
      } else if (role === "trade" && !onboardingComplete) {
        // Registered but never finished onboarding: resume at the right step.
        router.replace("/onboarding?resume=1");
      } else if (role === "trade") {
        router.replace("/(trade)/dashboard");
      } else if (role === "customer") {
        router.replace("/(customer)/requests");
      }
    }
  }, [isAuthenticated, role, onboardingComplete, isRegistering, paywallRequired, router]);

  return <EntryScreen />;
}
