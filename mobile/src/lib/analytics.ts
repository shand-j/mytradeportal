import Constants from "expo-constants";
import { AppState, AppStateStatus, Platform } from "react-native";
import { config } from "./config";
import { tokenStorage } from "./tokenStorage";

export type AnalyticsCategory = "screen_view" | "action" | "error" | "performance" | "session";
export type AnalyticsValue = string | number | boolean | null;
export type AnalyticsProperties = Record<string, AnalyticsValue>;

type AnalyticsEvent = {
  category: AnalyticsCategory;
  name: string;
  occurred_at: string;
  session_id: string;
  properties: AnalyticsProperties;
};

type ErrorUtilsLike = {
  getGlobalHandler: () => (error: unknown, isFatal?: boolean) => void;
  setGlobalHandler: (handler: (error: unknown, isFatal?: boolean) => void) => void;
};

const FLUSH_INTERVAL_MS = 15_000;
const BATCH_SIZE = 20;
const MAX_QUEUE_SIZE = 100;
const API_SUCCESS_SAMPLE_RATE = 0.1;
const startedAt = Date.now();
let sessionId = createId();
let queue: AnalyticsEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let flushInFlight = false;

function createId(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    const value = character === "x" ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
}

export function normaliseRoute(path: string): string {
  const cleanPath = path.split("?")[0].split("#")[0] || "/";
  return cleanPath
    .split("/")
    .map((segment) => {
      if (/^\d+$/.test(segment)) return ":id";
      if (/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(segment)) {
        return ":id";
      }
      return /^[A-Za-z0-9_-]{16,}$/.test(segment) ? ":id" : segment;
    })
    .join("/")
    .slice(0, 200);
}

function screenName(route: string): string {
  const name = route
    .replace(/[()[\]]/g, "")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  return (name || "root").slice(0, 80);
}

function baseProperties(): AnalyticsProperties {
  return {
    platform: Platform.OS,
    app_version: Constants.expoConfig?.version ?? "unknown",
    build_number: Constants.expoConfig?.ios?.buildNumber ?? "unknown",
    os_version: String(Platform.Version),
  };
}

function scheduleFlush(): void {
  if (flushTimer || flushInFlight || queue.length === 0) return;
  flushTimer = setTimeout(() => {
    flushTimer = null;
    void flushAnalytics();
  }, FLUSH_INTERVAL_MS);
}

function sanitiseProperties(properties: AnalyticsProperties): AnalyticsProperties {
  return Object.fromEntries(
    Object.entries(properties).map(([key, value]) => [
      key,
      ["path", "previous_route", "route"].includes(key) && typeof value === "string"
        ? normaliseRoute(value)
        : value,
    ]),
  );
}

export function captureAnalytics(
  category: AnalyticsCategory,
  name: string,
  properties: AnalyticsProperties = {},
): void {
  queue.push({
    category,
    name,
    occurred_at: new Date().toISOString(),
    session_id: sessionId,
    properties: { ...baseProperties(), ...sanitiseProperties(properties) },
  });
  if (queue.length > MAX_QUEUE_SIZE) queue = queue.slice(-MAX_QUEUE_SIZE);
  if (queue.length >= BATCH_SIZE) {
    void flushAnalytics();
  } else {
    scheduleFlush();
  }
}

export async function flushAnalytics(): Promise<void> {
  if (flushInFlight || queue.length === 0 || !config.apiBaseUrl) return;
  const [token, tenantId] = await Promise.all([
    tokenStorage.getToken(),
    tokenStorage.getTenantId(),
  ]);
  if (!token || !tenantId) return;

  flushInFlight = true;
  const batch = queue.splice(0, BATCH_SIZE);
  try {
    const response = await fetch(`${config.apiBaseUrl}/analytics/events`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        "X-Tenant-ID": tenantId,
      },
      body: JSON.stringify({ events: batch }),
    });
    if (!response.ok && response.status >= 500) {
      queue = [...batch, ...queue].slice(-MAX_QUEUE_SIZE);
    }
  } catch {
    queue = [...batch, ...queue].slice(-MAX_QUEUE_SIZE);
  } finally {
    flushInFlight = false;
    if (queue.length > 0) scheduleFlush();
  }
}

export function resetAnalyticsSession(): void {
  queue = [];
  sessionId = createId();
  captureAnalytics("session", "session_started", { source: "auth_change" });
}

export function trackScreen(route: string, previousRoute?: string): void {
  const normalised = normaliseRoute(route);
  captureAnalytics("screen_view", screenName(normalised), {
    route: normalised,
    previous_route: previousRoute ? normaliseRoute(previousRoute) : null,
  });
}

export function trackAction(name: string, properties: AnalyticsProperties = {}): void {
  captureAnalytics("action", name, properties);
}

export function trackError(name: string, properties: AnalyticsProperties = {}): void {
  captureAnalytics("error", name, properties);
}

export function trackPerformance(name: string, durationMs: number, properties: AnalyticsProperties = {}): void {
  captureAnalytics("performance", name, {
    ...properties,
    duration_ms: Math.round(durationMs * 100) / 100,
  });
}

export function shouldSampleApiSuccess(): boolean {
  return Math.random() < API_SUCCESS_SAMPLE_RATE;
}

export function startAnalyticsLifecycle(): () => void {
  trackPerformance("app_start", Date.now() - startedAt, { load_kind: "cold_start" });
  captureAnalytics("session", "app_open", { source: "lifecycle" });

  const subscription = AppState.addEventListener("change", (state: AppStateStatus) => {
    if (state === "active") {
      captureAnalytics("session", "app_foreground", { source: "lifecycle" });
      void flushAnalytics();
    } else if (state === "background" || state === "inactive") {
      captureAnalytics("session", "app_background", { source: "lifecycle" });
      void flushAnalytics();
    }
  });

  const errorUtils = (globalThis as { ErrorUtils?: ErrorUtilsLike }).ErrorUtils;
  const previousHandler = errorUtils?.getGlobalHandler();
  errorUtils?.setGlobalHandler((error, isFatal) => {
    const errorType = error instanceof Error ? error.name : "unknown_error";
    trackError("unhandled_js_error", {
      error_type: errorType,
      outcome: isFatal ? "fatal" : "non_fatal",
    });
    void flushAnalytics();
    previousHandler?.(error, isFatal);
  });

  return () => {
    subscription.remove();
    if (errorUtils && previousHandler) errorUtils.setGlobalHandler(previousHandler);
    void flushAnalytics();
  };
}
