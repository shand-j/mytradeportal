/**
 * Portal-mode host resolution.
 *
 * Tenant subdomains ({slug}.mytradeportal.co.uk) serve the tenant-branded
 * customer portal from this same bundle; www / apex / localhost / bare IPs
 * serve the marketing site. The slug comes from the first hostname label,
 * with two dev overrides (highest priority first):
 *
 *   1. `?slug=<slug>` query param — e.g. http://localhost:3000/?slug=demo
 *   2. VITE_PORTAL_SLUG env var — forces portal mode for a whole dev server
 */

const BASE_DOMAIN: string = import.meta.env.VITE_PORTAL_BASE_DOMAIN ?? 'mytradeportal.co.uk'

const RESERVED_LABELS = new Set(['www', 'apex'])

function isIpAddress(hostname: string): boolean {
  return /^\d{1,3}(\.\d{1,3}){3}$/.test(hostname) || hostname.includes(':')
}

function slugFromHostname(hostname: string): string | null {
  if (!hostname || isIpAddress(hostname) || hostname === 'localhost') return null
  // Local subdomain dev: {slug}.localhost
  if (hostname.endsWith('.localhost')) {
    const first = hostname.slice(0, -'.localhost'.length)
    return first && !RESERVED_LABELS.has(first) ? first : null
  }
  if (hostname === BASE_DOMAIN || hostname === `www.${BASE_DOMAIN}`) return null
  if (hostname.endsWith(`.${BASE_DOMAIN}`)) {
    const first = hostname.slice(0, -(`.${BASE_DOMAIN}`.length))
    // Multi-label prefixes (a.b.mytradeportal.co.uk) are not tenant slugs.
    if (first.includes('.')) return null
    return first && !RESERVED_LABELS.has(first) ? first : null
  }
  return null
}

/**
 * The tenant slug for portal mode, or null when the marketing site should
 * render. Resolved once per page load by App.
 */
export function resolvePortalSlug(): string | null {
  const params = new URLSearchParams(window.location.search)
  const override = params.get('slug')
  if (override) return override
  const envSlug = import.meta.env.VITE_PORTAL_SLUG as string | undefined
  if (envSlug) return envSlug
  return slugFromHostname(window.location.hostname)
}

/** True when this page load is serving the tenant customer portal. */
export function isPortalMode(): boolean {
  return resolvePortalSlug() !== null
}

/**
 * Absolute URL for a tenant's portal, preserving the current protocol/port —
 * used by the 6-digit code box to bounce www visitors onto their
 * electrician's subdomain.
 */
export function portalUrlForSlug(slug: string): string {
  const { protocol, hostname, port } = window.location
  let host: string
  if (hostname === 'localhost' || isIpAddress(hostname) || hostname.endsWith('.localhost')) {
    host = `${slug}.localhost`
  } else if (hostname === BASE_DOMAIN || hostname === `www.${BASE_DOMAIN}`) {
    host = `${slug}.${BASE_DOMAIN}`
  } else {
    // Already on a subdomain (or an unrecognised host) — swap the first label.
    host = hostname.replace(/^[^.]+/, slug)
  }
  return `${protocol}//${host}${port ? `:${port}` : ''}/`
}
