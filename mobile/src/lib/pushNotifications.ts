import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import Constants from "expo-constants";

/**
 * First-launch permission prompts + Expo push token registration.
 *
 * The system prompts (notifications + location) are shown at most once per
 * install — a flag is persisted in the iOS Keychain (localStorage on web).
 * Push-token registration is NOT gated by that flag: it runs on every call
 * once notification permission is granted, so a token that failed to register
 * on a previous launch (e.g. backend unreachable) is retried. The backend
 * upserts, so re-registering is idempotent.
 * Everything here is best-effort: the simulator has no push capability and
 * denied permissions are fine, so failures are logged and swallowed.
 */

const PROMPTED_KEY = "mtp_permissions_prompted_v1";

const isWeb = Platform.OS === "web";

async function getFlag(key: string): Promise<string | null> {
  if (isWeb) {
    return globalThis.localStorage?.getItem(key) ?? null;
  }
  return SecureStore.getItemAsync(key);
}

async function setFlag(key: string, value: string): Promise<void> {
  if (isWeb) {
    globalThis.localStorage?.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

/** Show a local notification for a newly arrived quote_ready notification. */
export async function fireLocalQuoteReadyAlert(title: string, body: string): Promise<void> {
  if (isWeb) return;
  try {
    const Notifications = await import("expo-notifications");
    await Notifications.scheduleNotificationAsync({
      content: { title, body },
      trigger: null,
    });
  } catch (err) {
    console.log("Local notification failed:", err);
  }
}

/** Configure foreground presentation so local alerts show while the app is open. */
export async function setupNotificationHandler(): Promise<void> {
  if (isWeb) return;
  try {
    const Notifications = await import("expo-notifications");
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: true,
        shouldSetBadge: true,
      }),
    });
  } catch (err) {
    console.log("Notification handler setup failed:", err);
  }
}

/** POST /notifications/push-token (staff or customer variant). */
async function postPushToken(role: "trade" | "customer", token: string): Promise<void> {
  // Dynamic import keeps this lib free of a static cycle with the API module.
  const { registerPushToken } = await import("../api/notifications");
  await registerPushToken(role, token, Platform.OS);
}

/** Send a device-side diagnostic line to the server logs; never throws. */
async function reportDiagnostic(message: string, context: Record<string, unknown>): Promise<void> {
  try {
    const { reportClientLog } = await import("../api/notifications");
    await reportClientLog(message, context);
  } catch {
    // Diagnostics are best-effort on top of an already-failing path.
  }
}

/**
 * On first launch after login, request notification + location permissions
 * (once per install). On every call — including later launches — register the
 * Expo push token with the backend whenever notification permission is
 * granted, so a registration that previously failed is retried.
 * Safe to call on every screen mount.
 */
export async function requestFirstLaunchPermissions(role: "trade" | "customer"): Promise<void> {
  if (isWeb) return;
  try {
    const prompted = await getFlag(PROMPTED_KEY);

    const [Notifications, Location] = await Promise.all([
      import("expo-notifications"),
      import("expo-location"),
    ]);

    if (!prompted) {
      await Notifications.requestPermissionsAsync().catch((err) => {
        console.log("Notification permission request failed:", err);
      });
      await Location.requestForegroundPermissionsAsync().catch((err) => {
        console.log("Location permission request failed:", err);
      });

      await setFlag(PROMPTED_KEY, "1");
    }

    // Re-ask whenever permission is not yet granted: iOS shows the system
    // prompt only while the decision is undetermined and returns the current
    // decision otherwise, so this recovers prompts interrupted on first
    // launch — it cannot re-prompt a user who already tapped "Don't Allow".
    let permissions = await Notifications.getPermissionsAsync();
    if (!permissions.granted) {
      permissions =
        (await Notifications.requestPermissionsAsync().catch((err) => {
          console.log("Notification permission request failed:", err);
          return null;
        })) ?? permissions;
    }

    if (!permissions.granted) {
      console.log(`Push registration skipped: permission '${permissions.status}'`);
      await reportDiagnostic("push_registration_skipped", {
        role,
        status: permissions.status,
        canAskAgain: permissions.canAskAgain,
        iosStatus: permissions.ios?.status ?? null,
      });
      return;
    }

    try {
      // Pass the EAS project id explicitly: the implicit fallback depends on
      // runtime config resolution, which can silently produce a token bound
      // to the wrong experience after OTA updates.
      const projectId = Constants.expoConfig?.extra?.eas?.projectId as string | undefined;
      const token = await Notifications.getExpoPushTokenAsync(
        projectId ? { projectId } : undefined
      );
      await postPushToken(role, token.data);
      console.log("Push token registered with backend");
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      console.log("Push token registration failed:", err);
      await reportDiagnostic("push_registration_failed", { role, error: detail });
    }
  } catch (err) {
    console.log("First-launch permission flow failed:", err);
  }
}
