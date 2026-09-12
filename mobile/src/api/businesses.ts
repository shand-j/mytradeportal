import { api } from "../lib/apiClient";
import { BusinessConfig } from "../types";

type PublicConfigResponse = {
  slug: string;
  code: string | null;
  name: string;
  logoUrl: string | null;
  primaryColor: string;
  secondaryColor: string;
  businessServices: string[];
  contactPhone: string | null;
  address: string | null;
};

type CurrentTenantResponse = {
  slug: string;
  code: string | null;
  name: string;
  logoUrl: string | null;
  primaryColor: string;
  secondaryColor: string;
  phone: string | null;
  address: string | null;
  /** Free-form tenant settings; bank payment details live here. */
  settings?: TenantSettings | null;
  /** Onboarding quoting metrics, when the tenant provided them. */
  quotesPerWeek?: number | null;
  avgMinutesPerQuote?: number | null;
};

/** Tenant settings keys the app reads/writes directly (camelized on the wire). */
type TenantSettings = {
  bankAccountName?: string;
  bankSortCode?: string;
  bankAccountNumber?: string;
  [key: string]: unknown;
};

const CODE_REGEX = /^\d{6}$/;

function normalizeConfig(data: PublicConfigResponse): BusinessConfig {
  return {
    slug: data.slug,
    code: data.code ?? data.slug,
    name: data.name,
    primaryColor: data.primaryColor,
    secondaryColor: data.secondaryColor,
    logoUrl: data.logoUrl ?? undefined,
    businessServices: data.businessServices ?? [],
    contactPhone: data.contactPhone ?? undefined,
    address: data.address ?? undefined,
  };
}

/**
 * Fetch a business's public white-label config by slug or 6-digit code (no auth required).
 *
 * Six-digit numeric input is routed through the dedicated by-code endpoint so
 * homeowners can find an electrician by typing their customer code.
 */
export async function fetchPublicConfig(slugOrCode: string): Promise<BusinessConfig> {
  const isCode = CODE_REGEX.test(slugOrCode.trim());

  if (isCode) {
    const data = await api.get<PublicConfigResponse>(
      `/businesses/by-code/${encodeURIComponent(slugOrCode.trim())}/public-config`,
      { auth: false }
    );
    return normalizeConfig(data);
  }

  const data = await api.get<PublicConfigResponse>(
    `/businesses/${encodeURIComponent(slugOrCode.trim())}/public-config`,
    { auth: false }
  );
  return normalizeConfig(data);
}

function normalizeTenant(tenant: CurrentTenantResponse): BusinessConfig {
  return {
    slug: tenant.slug,
    code: tenant.code ?? tenant.slug,
    name: tenant.name,
    primaryColor: tenant.primaryColor,
    secondaryColor: tenant.secondaryColor,
    logoUrl: tenant.logoUrl ?? undefined,
    businessServices: [],
    contactPhone: tenant.phone ?? undefined,
    address: tenant.address ?? undefined,
    quotesPerWeek: tenant.quotesPerWeek ?? undefined,
    avgMinutesPerQuote: tenant.avgMinutesPerQuote ?? undefined,
  };
}

/** Fetch the authenticated user's own tenant (trade users). */
export async function fetchCurrentTenant(): Promise<BusinessConfig> {
  const data = await api.get<CurrentTenantResponse>("/tenants/me");
  return normalizeTenant(data);
}

export type UpdateTenantInput = {
  name?: string;
  phone?: string;
  address?: string;
  primaryColor?: string;
};

/** Persist branding/business details for the authenticated user's tenant. */
export async function updateCurrentTenant(input: UpdateTenantInput): Promise<BusinessConfig> {
  const data = await api.patch<CurrentTenantResponse>("/tenants/me", input);
  return normalizeTenant(data);
}

export type PaymentDetails = {
  bankAccountName: string;
  bankSortCode: string;
  bankAccountNumber: string;
};

/** Fetch the tenant's bank-transfer payment details (shown on invoice emails). */
export async function fetchPaymentDetails(): Promise<PaymentDetails> {
  const data = await api.get<CurrentTenantResponse>("/tenants/me");
  const settings = data.settings ?? {};
  return {
    bankAccountName: settings.bankAccountName ?? "",
    bankSortCode: settings.bankSortCode ?? "",
    bankAccountNumber: settings.bankAccountNumber ?? "",
  };
}

/** Save the tenant's bank-transfer payment details into tenant settings. */
export async function updatePaymentDetails(input: PaymentDetails): Promise<PaymentDetails> {
  const data = await api.patch<CurrentTenantResponse>("/tenants/me", {
    settings: {
      bankAccountName: input.bankAccountName,
      bankSortCode: input.bankSortCode,
      bankAccountNumber: input.bankAccountNumber,
    },
  });
  const settings = data.settings ?? {};
  return {
    bankAccountName: settings.bankAccountName ?? "",
    bankSortCode: settings.bankSortCode ?? "",
    bankAccountNumber: settings.bankAccountNumber ?? "",
  };
}
