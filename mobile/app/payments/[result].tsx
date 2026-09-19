import { useEffect } from "react";
import { useRouter } from "expo-router";
import { Screen } from "../../src/components/ui/Screen";
import { Text } from "../../src/components/ui/Text";

/**
 * Landing route for the mtp://payments/stripe-return and stripe-refresh deep
 * links Stripe redirects to at the end of in-app Connect onboarding. The
 * in-app browser session closes itself; this route just pops back to whatever
 * launched the flow (app onboarding or Settings → Payments), which refetches
 * the payments status.
 */
export default function PaymentsReturnRoute() {
  const router = useRouter();
  useEffect(() => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/");
    }
  }, [router]);

  return (
    <Screen>
      <Text variant="body" color="secondary">
        Returning to the app…
      </Text>
    </Screen>
  );
}
