import { api } from "../lib/apiClient";
import { tokenStorage } from "../lib/tokenStorage";
import { useQuery } from "@tanstack/react-query";

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
  tenantSlug: string;
  user: ApiUser;
};

/**
 * Authenticate a tradesperson/staff user and persist the Bearer token + tenant id.
 * Throws ApiError (bad credentials) or NetworkError (backend unreachable).
 */
export async function loginWithToken(
  email: string,
  password: string,
  tenantSlug?: string
): Promise<{ user: ApiUser; tenantSlug: string }> {
  const data = await api.post<TokenResponse>(
    "/auth/token",
    { email, password, tenantSlug },
    { auth: false }
  );
  await tokenStorage.save(data.accessToken, data.user.tenantId);
  return { user: data.user, tenantSlug: data.tenantSlug };
}

export async function fetchMe(): Promise<ApiUser> {
  return api.get<ApiUser>("/auth/me");
}

export async function logoutToken(): Promise<void> {
  await tokenStorage.clear();
}

/**
 * Kick off a password-reset flow — the API always returns the same generic
 * message so it can be safely called from unauthenticated screens.
 */
export async function requestPasswordReset(email: string): Promise<void> {
  await api.post(
    "/auth/password-reset/request",
    { email },
    { auth: false }
  );
}

/** Complete a password-reset flow using the token from the email link. */
export async function confirmPasswordReset(
  token: string,
  newPassword: string
): Promise<void> {
  await api.post(
    "/auth/password-reset/confirm",
    { token, new_password: newPassword },
    { auth: false }
  );
}

/** Homeowner (customer) account returned by the customer portal. */
export type ApiCustomer = {
  id: string;
  tenantId: string;
  email: string;
  fullName: string;
  phone: string | null;
  address?: string | null;
  postcode?: string | null;
  /** Persisted property details, used to pre-fill repeat quote requests. */
  propertyProfile?: Record<string, unknown>;
  preferredContactMethod?: string | null;
  marketingConsent?: boolean;
};

type CustomerTokenResponse = {
  accessToken: string;
  tokenType: string;
  customer: ApiCustomer;
};

/** Register a homeowner against a business (by slug) and persist the token. */
export async function registerCustomer(
  slug: string,
  input: {
    fullName: string;
    email: string;
    phone?: string;
    password: string;
    address?: string;
    postcode?: string;
    preferredContactMethod?: string;
    quoteRequestId?: string;
  }
): Promise<ApiCustomer> {
  const data = await api.post<CustomerTokenResponse>(
    "/customer/register",
    { slug, ...input },
    { auth: false }
  );
  await tokenStorage.save(data.accessToken, data.customer.tenantId);
  return data.customer;
}

/**
 * Authenticate a homeowner and persist the token + tenant id.
 * The slug is optional: when omitted, the backend locates the account by
 * email across tenants (newest wins). The tenant is identified from the
 * returned token/customer either way.
 */
export async function loginCustomer(
  slug: string | undefined,
  email: string,
  password: string
): Promise<ApiCustomer> {
  const data = await api.post<CustomerTokenResponse>(
    "/customer/login",
    { ...(slug ? { slug } : {}), email, password },
    { auth: false }
  );
  await tokenStorage.save(data.accessToken, data.customer.tenantId);
  return data.customer;
}

/** The authenticated homeowner's own profile (customer token). */
export async function fetchCustomerMe(): Promise<ApiCustomer> {
  return api.get<ApiCustomer>("/customer/me");
}

/** TanStack Query hook for the logged-in customer's profile. */
export function useCustomerMe(enabled = true) {
  const query = useQuery({
    queryKey: ["customer-me"],
    queryFn: fetchCustomerMe,
    enabled,
  });

  return {
    customer: query.data,
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}
