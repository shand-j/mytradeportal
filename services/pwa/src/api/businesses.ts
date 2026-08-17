import { api } from "../lib/apiClient";
import { BusinessConfig } from "../types";

/** White-label config from GET /businesses/{slug}/public-config (already camelCase). */
type PublicConfigResponse = {
  slug: string;
  name: string;
  logoUrl: string | null;
  primaryColor: string;
  secondaryColor: string;
  businessServices: string[];
  contactPhone: string | null;
  address: string | null;
};

/**
 * Fetch a business's public white-label config by slug (no auth). Maps into the
 * app's `BusinessConfig`. The backend has no 6-digit code concept, so `code` is
 * set to the slug used for the lookup.
 */
export async function fetchPublicConfig(slug: string): Promise<BusinessConfig> {
  const data = await api.get<PublicConfigResponse>(
    `/businesses/${encodeURIComponent(slug)}/public-config`,
    { auth: false }
  );
  return {
    slug: data.slug,
    code: data.slug,
    name: data.name,
    primaryColor: data.primaryColor,
    secondaryColor: data.secondaryColor,
    logoUrl: data.logoUrl ?? undefined,
    businessServices: data.businessServices ?? [],
    contactPhone: data.contactPhone ?? undefined,
    address: data.address ?? undefined,
  };
}
