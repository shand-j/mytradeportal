/**
 * Server datetime parsing.
 *
 * The API persists datetimes in naive UTC columns and serialises them without
 * a timezone offset (e.g. "2026-10-24T07:00:00"). `new Date(...)` treats such
 * strings as device-LOCAL time, shifting every rendered time by the local
 * offset (an hour in BST). parseServerDate pins naive date-time strings to
 * UTC; strings that already carry `Z` or an explicit offset pass through
 * unchanged, as do date-only strings ("2026-10-24", which JS already parses
 * as UTC midnight).
 */

const TIME_COMPONENT = /T\d{2}:\d{2}/;
const UTC_OFFSET = /(Z|[+-]\d{2}:?\d{2})$/i;

/**
 * Parse a server datetime string, treating naive date-times as UTC.
 * Returns null for missing or unparseable input.
 */
export function parseServerDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const source =
    TIME_COMPONENT.test(trimmed) && !UTC_OFFSET.test(trimmed) ? `${trimmed}Z` : trimmed;
  const date = new Date(source);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Local (not UTC) calendar date "YYYY-MM-DD", so entries bucket into the day the user sees. */
export function toLocalIsoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
