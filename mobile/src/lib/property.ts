/** Property type options shared by the quote intake and the customer record. */
export const PROPERTY_TYPES = ["House", "Flat", "Bungalow", "Commercial"];

/** Bedroom count options shared by the quote intake and the customer record. */
export const BEDROOMS = ["1", "2", "3", "4", "5+"];

/** Customer-facing property types (quote-request wizard) -> shared options. */
const PROPERTY_TYPE_MAP: Record<string, string> = {
  house: "House",
  detached: "House",
  semi: "House",
  "semi-detached": "House",
  semi_detached: "House",
  terrace: "House",
  terraced: "House",
  flat: "Flat",
  apartment: "Flat",
  maisonette: "Flat",
  bungalow: "Bungalow",
  commercial: "Commercial",
};

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** Normalise a free-form property type onto the shared options. */
export function matchPropertyType(value: unknown): string {
  const raw = asString(value).trim().toLowerCase();
  if (!raw) return "";
  return PROPERTY_TYPE_MAP[raw] ?? (PROPERTY_TYPES.includes(asString(value)) ? asString(value) : "");
}

/** Normalise a bedroom count onto the shared options. */
export function matchBedrooms(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value >= 5 ? "5+" : BEDROOMS.includes(String(value)) ? String(value) : "";
  }
  const raw = asString(value).trim();
  if (!raw) return "";
  if (BEDROOMS.includes(raw)) return raw;
  const parsed = parseInt(raw, 10);
  if (Number.isNaN(parsed)) return "";
  return parsed >= 5 ? "5+" : BEDROOMS.includes(String(parsed)) ? String(parsed) : "";
}
