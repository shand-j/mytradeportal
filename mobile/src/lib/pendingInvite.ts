import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

/**
 * Remembers the email address a pending invitee typed on the login screen
 * when they asked for their invite link, so the login form can pre-fill it
 * once they've set a password. Mirrors tokenStorage's web fallback.
 */
const INVITE_EMAIL_KEY = "mtp_pending_invite_email";

const isWeb = Platform.OS === "web";

export const pendingInviteStorage = {
  async getEmail(): Promise<string | null> {
    if (isWeb) {
      return globalThis.localStorage?.getItem(INVITE_EMAIL_KEY) ?? null;
    }
    return SecureStore.getItemAsync(INVITE_EMAIL_KEY);
  },
  async saveEmail(email: string): Promise<void> {
    if (isWeb) {
      globalThis.localStorage?.setItem(INVITE_EMAIL_KEY, email);
      return;
    }
    await SecureStore.setItemAsync(INVITE_EMAIL_KEY, email);
  },
  async clear(): Promise<void> {
    if (isWeb) {
      globalThis.localStorage?.removeItem(INVITE_EMAIL_KEY);
      return;
    }
    await SecureStore.deleteItemAsync(INVITE_EMAIL_KEY);
  },
};
