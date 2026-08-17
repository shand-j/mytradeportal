import { useEffect } from "react";
import { useRouter } from "expo-router";
import { EntryScreen } from "../src/screens/entry/EntryScreen";
import { useAuth } from "../src/contexts/AuthContext";
import { useBusinessStore } from "../src/stores/businessStore";
import { fetchPublicConfig } from "../src/api/businesses";
import { config } from "../src/lib/config";

export default function Index() {
  const { isAuthenticated, role, onboardingComplete, isRegistering } = useAuth();
  const router = useRouter();
  const business = useBusinessStore((state) => state.business);
  const setBusiness = useBusinessStore((state) => state.setBusiness);

  // White-label bootstrap: a per-tenant build targets one business slug. When
  // connected, fetch its public config once and theme the app for that tenant.
  useEffect(() => {
    if (config.apiEnabled && config.businessSlug && !business) {
      fetchPublicConfig(config.businessSlug)
        .then(setBusiness)
        .catch(() => {
          // Unknown slug or offline — stay on the generic/demo experience.
        });
    }
  }, [business, setBusiness]);

  useEffect(() => {
    // Registration sets isRegistering before a user exists, so route into the
    // onboarding wizard on that alone.
    if (role === "trade" && isRegistering) {
      router.replace("/onboarding");
      return;
    }
    if (isAuthenticated && role !== "guest") {
      if (role === "trade" && !onboardingComplete) {
        router.replace("/onboarding");
      } else if (role === "trade") {
        router.replace("/(trade)/dashboard");
      } else if (role === "customer") {
        router.replace("/(customer)/requests");
      }
    }
  }, [isAuthenticated, role, onboardingComplete, isRegistering, router]);

  return <EntryScreen />;
}
