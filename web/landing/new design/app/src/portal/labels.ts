/**
 * Customer-facing labels for API enum values.
 *
 * The API exposes raw enum keys (e.g. `consumer_unit`, and older tenants may
 * carry the SHOUTY_CASE form `CONSUMER_UNIT`). Never render those to
 * customers — map them through here. Labels mirror the mobile app's intake
 * option sets (`mobile/src/screens/onboarding/steps/ServicesStep.tsx`).
 */

const SERVICE_CATEGORY_LABELS: Record<string, string> = {
  ev_charger: 'EV charger',
  consumer_unit: 'Consumer unit',
  full_rewire: 'Full rewire',
  partial_rewire: 'Partial rewire',
  eicr: 'EICR',
  additional_points: 'Additional points',
  outdoor_power: 'Outdoor power',
  fault_finding: 'Fault finding',
  smart_home: 'Smart home',
  lighting_design: 'Lighting design',
  data_networking: 'Data networking',
  emergency_callout: 'Emergency callout',
  other: 'Something else',
}

/** `CONSUMER_UNIT` / `consumer-unit` → `Consumer unit` (acronyms preserved). */
export function humanizeEnum(value: string): string {
  const words = value
    .trim()
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((word) => word.toLowerCase())
  if (words.length === 0) return value
  return words
    .map((word, index) => (index === 0 ? word[0].toUpperCase() + word.slice(1) : word))
    .join(' ')
}

export function serviceCategoryLabel(key: string): string {
  const normalized = key.trim().toLowerCase().replace(/[\s-]+/g, '_')
  return SERVICE_CATEGORY_LABELS[normalized] ?? humanizeEnum(key)
}
