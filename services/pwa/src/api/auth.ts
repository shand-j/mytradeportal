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

/** Homeowner (customer) account returned by the customer portal. */
export type ApiCustomer = {
  id: string;
  tenantId: string;
  email: string;
  fullName: string;
  phone: string | null;
};

type CustomerTokenResponse = {
  accessToken: string;
  tokenType: string;
  customer: ApiCustomer;
};

/**
 * Register a homeowner against a business (by slug) and persist the customer
 * token + tenant id. Throws ApiError (e.g. email already exists) or
 * NetworkError.
 */
export async function registerCustomer(
  slug: string,
  input: { fullName: string; email: string; phone?: string; password: string }
): Promise<ApiCustomer> {
  const data = await api.post<CustomerTokenResponse>(
    "/customer/register",
    { slug, ...input },
    { auth: false }
  );
  await tokenStorage.save(data.accessToken, data.customer.tenantId);
  return data.customer;
}

/** Authenticate a homeowner and persist the customer token + tenant id. */
export async function loginCustomer(
  slug: string,
  email: string,
  password: string
): Promise<ApiCustomer> {
  const data = await api.post<CustomerTokenResponse>(
    "/customer/login",
    { slug, email, password },
    { auth: false }
  );
  await tokenStorage.save(data.accessToken, data.customer.tenantId);
  return data.customer;
}
