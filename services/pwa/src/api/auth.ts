import { api } from "../lib/apiClient";
import { tokenStorage } from "../lib/tokenStorage";

export type ApiUser = {
  id: string;
  tenantId: string;
  email: string;
  fullName: string;
  role: string;
  isActive: boolean;
  phone: string | null;
};

type TokenResponse = {
  accessToken: string;
  tokenType: string;
  user: ApiUser;
};

/**
 * Authenticate against the backend and persist the Bearer token + tenant id.
 * Returns the authenticated user. Throws ApiError (bad credentials) or
 * NetworkError (backend unreachable), which callers use to fall back to demo
 * mode when appropriate.
 */
export async function loginWithToken(
  email: string,
  password: string,
  tenantSlug?: string
): Promise<ApiUser> {
  const data = await api.post<TokenResponse>(
    "/auth/token",
    { email, password, tenantSlug },
    { auth: false }
  );
  await tokenStorage.save(data.accessToken, data.user.tenantId);
  return data.user;
}

export async function fetchMe(): Promise<ApiUser> {
  return api.get<ApiUser>("/auth/me");
}

export async function logoutToken(): Promise<void> {
  await tokenStorage.clear();
}
