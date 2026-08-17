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
  identity?: Record<string, unknown>;
  compliance?: Record<string, unknown>;
  services?: string[];
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
    },
    { auth: false, headers: { "X-Setup-Token": config.setupToken } }
  );
}

async function completeStep(step: string, value: Record<string, unknown>): Promise<void> {
  await api.patch(`/onboarding/step/${step}`, { step, value });
}

/**
 * Provision a real business from the wizard: create the tenant + admin user,
 * authenticate, record the launch-gate onboarding steps, then launch. Returns
 * the authenticated admin user. Retries on slug collisions.
 *
 * Requires connected mode with a configured setup token; callers should guard
 * with `canRegisterOnline()` and fall back to demo completion otherwise.
 */
export async function registerBusiness(input: RegisterBusinessInput): Promise<ApiUser> {
  let slug = `${slugify(input.tradingName)}-${randomSuffix()}`;

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await createTenant(slug, input);
      break;
    } catch (err) {
      // Retry only on slug collision; surface everything else.
      if (err instanceof ApiError && err.status === 409 && attempt < 2) {
        slug = `${slugify(input.tradingName)}-${randomSuffix()}`;
        continue;
      }
      throw err;
    }
  }

  const user = await loginWithToken(input.email, input.password, slug);

  // Record the launch-gate steps from collected wizard data, then launch. The
  // backend stores these as free-form values, so shape is not strictly checked.
  await completeStep("business_identity", input.identity ?? { tradingName: input.tradingName });
  await completeStep("compliance", input.compliance ?? {});
  await completeStep("services", { services: input.services ?? [] });
  await api.post("/onboarding/launch");

  return user;
}

/** True when self-service online registration is possible (connected + token). */
export function canRegisterOnline(): boolean {
  return config.apiEnabled && config.setupToken.length > 0;
}
