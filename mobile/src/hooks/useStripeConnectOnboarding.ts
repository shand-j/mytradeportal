import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import { connectStripe } from "../api/payments";
import { ApiError, NetworkError } from "../lib/apiClient";

export type StripeConnectOnboarding = {
  /** Open Stripe onboarding in the in-app browser; resolves when it closes. */
  start: () => Promise<void>;
  connecting: boolean;
  error: string | null;
};

/**
 * Run Stripe Connect onboarding without leaving the app.
 *
 * The hosted AccountLink opens in an ASWebAuthenticationSession (in-app
 * browser) with mtp:// deep links as return/refresh URLs, so completing or
 * abandoning the flow lands back on the screen that launched it — never in
 * Safari. Afterwards the payments status query is refetched; the API syncs
 * the account flags from Stripe on every status read, so the UI reflects the
 * post-onboarding state with no manual refresh.
 *
 * TODO(#188): swap the AccountLink + in-app browser for Stripe's embedded
 * Connect onboarding component once @stripe/stripe-react-native is added —
 * POST /payments/connect/session already mints the AccountSession it needs.
 */
export function useStripeConnectOnboarding(): StripeConnectOnboarding {
  const queryClient = useQueryClient();
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setError(null);
    setConnecting(true);
    try {
      const returnUrl = Linking.createURL("/payments/stripe-return");
      const refreshUrl = Linking.createURL("/payments/stripe-refresh");
      const { onboardingUrl } = await connectStripe({ returnUrl, refreshUrl });
      await WebBrowser.openAuthSessionAsync(onboardingUrl, returnUrl);
      await queryClient.refetchQueries({ queryKey: ["payments", "status"] });
    } catch (err) {
      if (err instanceof NetworkError) {
        setError("Can't reach the server. Check your connection and try again.");
      } else if (err instanceof ApiError && err.status === 503) {
        setError("Card payments aren't available yet. Please try again later.");
      } else {
        setError("Couldn't start Stripe setup. Please try again.");
      }
    } finally {
      setConnecting(false);
    }
  };

  return { start, connecting, error };
}
