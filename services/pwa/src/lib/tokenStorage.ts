import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

/**
 * Secure token storage. Uses the iOS Keychain (expo-secure-store) on device and
 * localStorage on web (secure-store is unavailable on web). Tokens are the only
 * thing we persist client-side; everything else is server state via TanStack
 * Query.
 */
const TOKEN_KEY = "mtp_auth_token";
const TENANT_KEY = "mtp_tenant_id";

const isWeb = Platform.OS === "web";

async function setItem(key: string, value: string): Promise<void> {
  if (isWeb) {
    globalThis.localStorage?.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

async function getItem(key: string): Promise<string | null> {
  if (isWeb) {
    return globalThis.localStorage?.getItem(key) ?? null;
  }
  return SecureStore.getItemAsync(key);
}

async function removeItem(key: string): Promise<void> {
  if (isWeb) {
    globalThis.localStorage?.removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

export const tokenStorage = {
  getToken: () => getItem(TOKEN_KEY),
  getTenantId: () => getItem(TENANT_KEY),
  async save(token: string, tenantId: string): Promise<void> {
    await setItem(TOKEN_KEY, token);
    await setItem(TENANT_KEY, tenantId);
  },
  async clear(): Promise<void> {
    await removeItem(TOKEN_KEY);
    await removeItem(TENANT_KEY);
  },
};
