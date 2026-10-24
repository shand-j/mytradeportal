import { useEffect, useMemo, useState, type ComponentProps } from "react";
import {
  ConnectAccountOnboarding,
  ConnectComponentsProvider,
  loadConnectAndInitialize,
} from "@stripe/stripe-react-native";
import type { ConnectSessionRead } from "../../api/payments";

export type ConnectLoadError = Parameters<
  NonNullable<ComponentProps<typeof ConnectAccountOnboarding>["onLoadError"]>
>[0];

type EmbeddedStripeOnboardingProps = {
  session: ConnectSessionRead;
  fetchClientSecret: () => Promise<string>;
  onExit: () => void;
  onLoadError: (event: ConnectLoadError) => void;
  onUnavailable: () => void;
};

export function EmbeddedStripeOnboarding({
  session,
  fetchClientSecret,
  onExit,
  onLoadError,
  onUnavailable,
}: EmbeddedStripeOnboardingProps) {
  // The Stripe Connect embedded components render inside react-native-webview; if the
  // native module is missing the SDK spins forever, so probe for it up front.
  const [webviewAvailable, setWebviewAvailable] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    import("react-native-webview")
      .then(() => {
        if (!cancelled) setWebviewAvailable(true);
      })
      .catch(() => {
        if (!cancelled) setWebviewAvailable(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (webviewAvailable === false) onUnavailable();
  }, [webviewAvailable, onUnavailable]);

  const connectInstance = useMemo(
    () =>
      webviewAvailable
        ? loadConnectAndInitialize({
            publishableKey: session.publishableKey,
            fetchClientSecret,
            appearance: {
              variables: {
                colorPrimary: "#0F172A",
                colorBackground: "#FFFFFF",
              },
            },
          })
        : null,
    [fetchClientSecret, session.publishableKey, webviewAvailable]
  );

  if (!connectInstance) return null;

  return (
    <ConnectComponentsProvider connectInstance={connectInstance}>
      <ConnectAccountOnboarding
        title="Stripe setup"
        collectionOptions={{ fields: "currently_due", futureRequirements: "include" }}
        onExit={onExit}
        onLoadError={onLoadError}
      />
    </ConnectComponentsProvider>
  );
}
