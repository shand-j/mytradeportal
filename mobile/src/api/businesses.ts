import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";
import { camelizeKeys } from "../lib/case";
import { config } from "../lib/config";
import { tokenStorage } from "../lib/tokenStorage";
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
  reviewUrl: string | null;
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
  quoteRemindersEnabled?: boolean;
  quoteReminderMax?: number;
  quoteReminderIntervalDays?: number;
  invoiceRemindersEnabled?: boolean;
  invoiceReminderIntervalDays?: number;
  quoteRounding?: number;
  workingDayStart?: string;
  workingDayEnd?: string;
  workingDays?: number[];
  /** Public review link (Google Reviews etc.) surfaced on the customer portal. */
  reviewUrl?: string;
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
    reviewUrl: data.reviewUrl ?? undefined,
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
    // The review link lives in the free-form settings JSONB (review_url).
    reviewUrl:
      typeof tenant.settings?.reviewUrl === "string" && tenant.settings.reviewUrl
        ? tenant.settings.reviewUrl
        : undefined,
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
  /** Public review link; PATCH /tenants/me flattens it into tenant settings. */
  reviewUrl?: string;
};

/** Persist branding/business details for the authenticated user's tenant. */
export async function updateCurrentTenant(input: UpdateTenantInput): Promise<BusinessConfig> {
  const data = await api.patch<CurrentTenantResponse>("/tenants/me", input);
  return normalizeTenant(data);
}

/** A logo image picked on-device, not yet uploaded. */
export type LogoAsset = {
  uri: string;
  name: string;
  type: string;
};

/**
 * Upload the tenant's business logo (staff). Multipart through the API —
 * MinIO is private-network-only, so devices never see storage URLs. The
 * server points settings.logo_url at the public GET /businesses/{slug}/logo
 * route; the response carries the new URL.
 */
export async function uploadTenantLogo(asset: LogoAsset): Promise<BusinessConfig> {
  const [token, tenantId] = await Promise.all([
    tokenStorage.getToken(),
    tokenStorage.getTenantId(),
  ]);
  const form = new FormData();
  // React Native and web File / Blob shapes differ; both are accepted by
  // FormData under `any` here without runtime pain.
  const blob =
    typeof File !== "undefined"
      ? await fetch(asset.uri).then((r) => r.blob())
      : ({ uri: asset.uri, name: asset.name, type: asset.type } as unknown as Blob);
  form.append("file", blob as Blob, asset.name);
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (tenantId) headers["X-Tenant-ID"] = tenantId;
  const response = await fetch(`${config.apiBaseUrl}/tenants/me/logo`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!response.ok) {
    let detail = `Upload failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (payload.detail) detail = String(payload.detail);
    } catch {
      // Non-JSON error body — keep the status-based message.
    }
    throw new Error(detail);
  }
  const data = camelizeKeys(await response.json()) as CurrentTenantResponse;
  return normalizeTenant(data);
}

/** Remove the tenant's logo (staff): clears the branding settings server-side. */
export async function removeTenantLogo(): Promise<BusinessConfig> {
  const data = await api.delete<CurrentTenantResponse>("/tenants/me/logo");
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

export type FollowUpSettings = {
  quoteRemindersEnabled: boolean;
  /** How many quote reminders to send before giving up (1-10). */
  quoteReminderMax: number;
  /** Days between the quote being sent / last reminder and the next one. */
  quoteReminderIntervalDays: number;
  invoiceRemindersEnabled: boolean;
  /** Days between the due date / last reminder and the next chase (recurs). */
  invoiceReminderIntervalDays: number;
  /** Round quote totals up to the nearest £5 or £10; 0 = off. */
  quoteRounding: number;
};

function clampInt(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, Math.round(parsed)));
}

/** Fetch the tenant's quote/invoice follow-up + rounding settings. */
export async function fetchFollowUpSettings(): Promise<FollowUpSettings> {
  const data = await api.get<CurrentTenantResponse>("/tenants/me");
  const s = data.settings ?? {};
  const rounding = Number(s.quoteRounding);
  return {
    quoteRemindersEnabled: s.quoteRemindersEnabled !== false,
    quoteReminderMax: clampInt(s.quoteReminderMax, 3, 1, 10),
    quoteReminderIntervalDays: clampInt(s.quoteReminderIntervalDays, 3, 1, 90),
    invoiceRemindersEnabled: s.invoiceRemindersEnabled !== false,
    invoiceReminderIntervalDays: clampInt(s.invoiceReminderIntervalDays, 7, 1, 90),
    quoteRounding: rounding === 5 || rounding === 10 ? rounding : 0,
  };
}

/** Save follow-up + rounding settings into tenant settings (merged server-side). */
export async function updateFollowUpSettings(input: FollowUpSettings): Promise<FollowUpSettings> {
  await api.patch<CurrentTenantResponse>("/tenants/me", {
    settings: {
      quoteRemindersEnabled: input.quoteRemindersEnabled,
      quoteReminderMax: input.quoteReminderMax,
      quoteReminderIntervalDays: input.quoteReminderIntervalDays,
      invoiceRemindersEnabled: input.invoiceRemindersEnabled,
      invoiceReminderIntervalDays: input.invoiceReminderIntervalDays,
      quoteRounding: input.quoteRounding,
    },
  });
  return input;
}

/**
 * The tenant's quote-total rounding increment (£5 or £10; 0 = off). Screens
 * that preview a total the backend will round (quote totals, scratch-invoice
 * totals) use this so the preview matches the stored value.
 */
export function useQuoteRoundingIncrement(): number {
  const query = useQuery({ queryKey: ["follow-up-settings"], queryFn: fetchFollowUpSettings });
  return query.data?.quoteRounding ?? 0;
}

export type WorkingHours = {
  /** "HH:MM" 24-hour. */
  workingDayStart: string;
  workingDayEnd: string;
  /** Weekday ints, Monday = 0 ... Sunday = 6. */
  workingDays: number[];
};

/** Fetch the tenant's working hours (defaults: 08:00-18:00, every day). */
export async function fetchWorkingHours(): Promise<WorkingHours> {
  const data = await api.get<CurrentTenantResponse>("/tenants/me");
  const s = data.settings ?? {};
  const days = Array.isArray(s.workingDays)
    ? s.workingDays.filter((d) => Number.isInteger(d) && d >= 0 && d <= 6)
    : [];
  return {
    workingDayStart: typeof s.workingDayStart === "string" ? s.workingDayStart : "08:00",
    workingDayEnd: typeof s.workingDayEnd === "string" ? s.workingDayEnd : "18:00",
    workingDays: days.length > 0 ? days : [0, 1, 2, 3, 4, 5, 6],
  };
}

/** Save working hours into tenant settings (merged server-side). */
export async function updateWorkingHours(input: WorkingHours): Promise<WorkingHours> {
  await api.patch<CurrentTenantResponse>("/tenants/me", {
    settings: {
      workingDayStart: input.workingDayStart,
      workingDayEnd: input.workingDayEnd,
      workingDays: input.workingDays,
    },
  });
  return input;
}
