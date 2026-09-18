import { api, ApiError } from "../lib/apiClient";
import { config } from "../lib/config";
import { loginWithToken, ApiUser } from "./auth";

/** Data collected by the onboarding wizard, needed to provision a real tenant. */
export type RegisterBusinessInput = {
  fullName: string;
  email: string;
  password: string;
  phone?: string;
  role?: string;
  tradingName: string;
  /** Trading address/postcode captured in onboarding; persisted on the tenant. */
  address?: string;
  postcode?: string;
  identity?: Record<string, unknown>;
  compliance?: Record<string, unknown>;
  services?: string[];
  /** Branding choices (primaryColor is snakeized to primary_color on the wire). */
  branding?: Record<string, unknown>;
  /** Tax step answers (vatRegistered etc.) — drive quote/invoice VAT rates. */
  tax?: Record<string, unknown>;
};

function slugify(name: string): string {
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  return base.length >= 2 ? base : "business";
}

function randomSuffix(): string {
  return Math.random().toString(36).slice(2, 7);
}

async function createTenant(slug: string, input: RegisterBusinessInput): Promise<void> {
  await api.post(
    "/tenants",
    {
      slug,
      name: input.tradingName,
      adminEmail: input.email,
      adminName: input.fullName,
      adminPassword: input.password,
      phone: input.phone,
      address: input.address,
      postcode: input.postcode,
    },
    { auth: false, headers: { "X-Setup-Token": config.setupToken } }
  );
}

async function completeStep(step: string, value: Record<string, unknown>): Promise<void> {
  await api.patch(`/onboarding/step/${step}`, { step, value });
}

export type OnboardingStatus = {
  status: string;
  onboardingProgress: Record<string, { completed: boolean; value: Record<string, unknown> }>;
  launchEnabled: boolean;
  pendingSteps: string[];
};

/**
 * Pre-flight duplicate-account check for the wizard's email step, so a user
 * who already has an account finds out while typing their email rather than
 * at the final registration step. Returns true when the email is free.
 */
export async function checkEmailAvailability(email: string): Promise<boolean> {
  const result = await api.get<{ email: string; available: boolean }>(
    `/tenants/email-availability?email=${encodeURIComponent(email)}`,
    { auth: false, headers: { "X-Setup-Token": config.setupToken } }
  );
  return result.available;
}

export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  return api.get<OnboardingStatus>("/onboarding/status");
}

/**
 * Resume path for users whose tenant already exists but whose onboarding
 * never completed (e.g. registration partially failed): re-record the wizard
 * steps and launch. Idempotent — the step endpoint overwrites.
 */
export async function completeOnboardingSteps(
  data: Record<string, unknown>
): Promise<void> {
  const identity = (data.identity ?? {}) as Record<string, unknown>;
  const compliance = (data.compliance ?? {}) as Record<string, unknown>;
  const services = (data.services ?? {}) as Record<string, unknown>;
  const branding = (data.branding ?? {}) as Record<string, unknown>;
  const tax = (data.tax ?? {}) as Record<string, unknown>;
  await completeStep("business_identity", identity);
  await completeStep("compliance", compliance);
  await completeStep("services", {
    services: (services.services as string[] | undefined) ?? [],
  });
  if (!branding.skipped && Object.keys(branding).length > 0) {
    await completeStep("branding", branding);
  }
  if (Object.keys(tax).length > 0) {
    await completeStep("tax", tax);
  }
  await api.post("/onboarding/launch");
}

/**
 * Provision a real business from the wizard: create the tenant + admin user,
 * authenticate, record the launch-gate onboarding steps, then launch.
 * Retries on slug collisions.
 */
export async function registerBusiness(input: RegisterBusinessInput): Promise<ApiUser> {
  let slug = `${slugify(input.tradingName)}-${randomSuffix()}`;

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await createTenant(slug, input);
      break;
    } catch (err) {
      // Retry only on slug collision; an email conflict means the account
      // already exists and the user should log in, not mint another tenant.
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        err.detail.toLowerCase().includes("slug") &&
        attempt < 2
      ) {
        slug = `${slugify(input.tradingName)}-${randomSuffix()}`;
        continue;
      }
      throw err;
    }
  }

  const { user } = await loginWithToken(input.email, input.password, slug);

  await completeStep("business_identity", input.identity ?? { tradingName: input.tradingName });
  await completeStep("compliance", input.compliance ?? {});
  await completeStep("services", { services: input.services ?? [] });
  if (input.branding) {
    await completeStep("branding", input.branding);
  }
  if (input.tax) {
    await completeStep("tax", input.tax);
  }
  await api.post("/onboarding/launch");

  return user;
}


