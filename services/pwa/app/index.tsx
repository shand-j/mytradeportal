import { useEffect } from "react";
import { useRouter } from "expo-router";
import { EntryScreen } from "../src/screens/entry/EntryScreen";
import { useAuth } from "../src/contexts/AuthContext";

export default function Index() {
  const { isAuthenticated, role, onboardingComplete, isRegistering } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isAuthenticated && role !== "guest") {
      if (role === "trade" && (!onboardingComplete || isRegistering)) {
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
