import { useCallback, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { createConnectSession, type ConnectSessionRead } from "../api/payments";
import {
  EmbeddedStripeOnboarding,
  type ConnectLoadError,
} from "../components/trade/EmbeddedStripeOnboarding";
import { ApiError, NetworkError } from "../lib/apiClient";

export type StripeConnectOnboarding = {
  start: () => Promise<void>;
  connecting: boolean;
  error: string | null;
  onboarding: ReactNode;
};

export function useStripeConnectOnboarding(): StripeConnectOnboarding {
  const queryClient = useQueryClient();
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<ConnectSessionRead | null>(null);
  const retriedExpiry = useRef(false);

  const showError = useCallback((err: unknown) => {
    if (err instanceof NetworkError) {
      setError("Can't reach the server. Check your connection and try again.");
    } else if (err instanceof ApiError && err.status === 503) {
      setError("Card payments aren't available yet. Please try again later.");
    } else {
      setError("Couldn't start Stripe setup. Please try again.");
    }
  }, []);

  const mintSession = useCallback(async () => {
    const nextSession = await createConnectSession();
    setSession(nextSession);
    return nextSession;
  }, []);

  const start = async () => {
    setError(null);
    setConnecting(true);
    retriedExpiry.current = false;
    try {
      await mintSession();
    } catch (err) {
      showError(err);
    } finally {
      setConnecting(false);
    }
  };

  const finish = async () => {
    setSession(null);
    setConnecting(true);
    await queryClient.refetchQueries({ queryKey: ["payments", "status"] });
    setConnecting(false);
  };

  const fetchClientSecret = useCallback(async () => {
    if (session) return session.clientSecret;
    return (await mintSession()).clientSecret;
  }, [mintSession, session]);

  const handleLoadError = ({ error: loadError }: ConnectLoadError) => {
    const expired = loadError.message?.toLowerCase().includes("expir");
    if (expired && !retriedExpiry.current) {
      retriedExpiry.current = true;
      setConnecting(true);
      void mintSession()
        .catch((err) => {
          setSession(null);
          showError(err);
        })
        .finally(() => setConnecting(false));
      return;
    }
    setSession(null);
    setError("Stripe setup couldn't load. Please try again.");
  };

  return {
    start,
    connecting,
    error,
    onboarding: session ? (
      <EmbeddedStripeOnboarding
        key={session.clientSecret}
        session={session}
        fetchClientSecret={fetchClientSecret}
        onExit={() => void finish()}
        onLoadError={handleLoadError}
      />
    ) : null,
  };
}
