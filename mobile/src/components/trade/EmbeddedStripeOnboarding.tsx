import { useMemo, type ComponentProps } from "react";
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
};

export function EmbeddedStripeOnboarding({
  session,
  fetchClientSecret,
  onExit,
  onLoadError,
}: EmbeddedStripeOnboardingProps) {
  const connectInstance = useMemo(
    () =>
      loadConnectAndInitialize({
        publishableKey: session.publishableKey,
        fetchClientSecret,
        appearance: {
          variables: {
            colorPrimary: "#0F172A",
            colorBackground: "#FFFFFF",
          },
        },
      }),
    [fetchClientSecret, session.publishableKey]
  );

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
