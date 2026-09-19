/**
 * UK locale formatting helpers for dates, money and enum labels.
 * Centralised so screens stop rendering US-style dates and raw enum values.
 */

const dateFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const gbpFormatter = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
});

/** Format a date as "02 Sep 2026" (en-GB). Returns "—" for missing/invalid input. */
export function formatDateUK(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return dateFormatter.format(date);
}

/** Format an amount as GBP with 2dp, e.g. £1,120.80. */
export function formatMoneyGBP(amount: number): string {
  return gbpFormatter.format(amount);
}

/**
 * Round a money total UP to the nearest multiple of `increment` (£513 → £515
 * at an increment of 5). Mirrors the backend's quote-rounding rule so client-
 * side previews match the stored totals; 0/negative increment disables it.
 */
export function roundUpToIncrement(total: number, increment: number): number {
  if (!Number.isFinite(total) || !Number.isFinite(increment) || increment <= 0) return total;
  const totalPence = Math.round(total * 100);
  const incrementPence = Math.round(increment * 100);
  if (incrementPence <= 0) return total;
  return (Math.ceil(totalPence / incrementPence) * incrementPence) / 100;
}

const URGENCY_LABELS: Record<string, string> = {
  emergency: "Emergency",
  emergency_today: "Emergency — today",
  today: "Today",
  this_week: "This week",
  this_month: "This month",
  flexible: "Flexible",
  just_researching: "Just researching",
  normal: "Normal",
};

/** Humanize a backend urgency enum ("this_week" -> "This week"). */
export function formatUrgency(urgency: string | null | undefined): string {
  if (!urgency) return "—";
  const known = URGENCY_LABELS[urgency];
  if (known) return known;
  const humanized = urgency.replace(/_/g, " ").trim();
  return humanized.charAt(0).toUpperCase() + humanized.slice(1);
}
