import { useEffect } from "react";
import type { ConnectSessionRead } from "../../api/payments";

// Structural twin of the native ConnectLoadError: the handler destructures
// { error: { message } }. Kept import-free of @stripe/stripe-react-native —
// that package pulls react-native internals that don't exist on web.
export type ConnectLoadError = { error: { message?: string } };

type EmbeddedStripeOnboardingProps = {
  session: ConnectSessionRead;
  fetchClientSecret: () => Promise<string>;
  onExit: () => void;
  onLoadError: (event: ConnectLoadError) => void;
  onUnavailable: () => void;
};

export function EmbeddedStripeOnboarding({ onUnavailable }: EmbeddedStripeOnboardingProps) {
  // Embedded Connect components are native-only; on web (the E2E harness)
  // degrade to the same "unavailable" path as a missing native module
  // instead of crashing the whole bundle at import time.
  useEffect(() => {
    onUnavailable();
  }, [onUnavailable]);

  return null;
}
