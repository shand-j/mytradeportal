import { usePathname } from "expo-router";
import { useEffect, useRef } from "react";
import {
  resetAnalyticsSession,
  startAnalyticsLifecycle,
  trackScreen,
} from "../lib/analytics";
import { useAuthStore } from "../stores/authStore";

export function AnalyticsLifecycle() {
  const pathname = usePathname();
  const previousPath = useRef<string | null>(null);
  const user = useAuthStore((state) => state.user);
  const role = useAuthStore((state) => state.role);
  const sessionRestored = useAuthStore((state) => state.sessionRestored);
  const identity = user ? `${role}:${user.id}` : "guest";

  useEffect(() => startAnalyticsLifecycle(), []);

  useEffect(() => {
    if (sessionRestored) resetAnalyticsSession();
  }, [identity, sessionRestored]);

  useEffect(() => {
    if (!sessionRestored || !pathname) return;
    trackScreen(pathname, previousPath.current ?? undefined);
    previousPath.current = pathname;
  }, [pathname, sessionRestored]);

  return null;
}
