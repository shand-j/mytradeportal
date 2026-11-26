import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router';
import {
  resetAnalyticsSession,
  startBrowserAnalytics,
  trackScreen,
} from '@/lib/analytics';
import { useAuthStore } from '@/stores/authStore';

export function AnalyticsLifecycle() {
  const location = useLocation();
  const previousPath = useRef<string | null>(null);
  const user = useAuthStore((state) => state.user);
  const isLoading = useAuthStore((state) => state.isLoading);
  const identity = user?.id ?? 'guest';

  useEffect(() => startBrowserAnalytics(), []);

  useEffect(() => {
    if (!isLoading) resetAnalyticsSession();
  }, [identity, isLoading]);

  useEffect(() => {
    if (isLoading) return;
    trackScreen(location.pathname, previousPath.current ?? undefined);
    previousPath.current = location.pathname;
  }, [isLoading, location.pathname]);

  return null;
}
