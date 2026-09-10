/**
 * Backend assertion helpers: REST API (tenant/user auth) and direct Postgres
 * reads for persistence checks. DB access uses the Railway TCP proxy with the
 * postgres role, which bypasses RLS — appropriate for test assertions only.
 */
import { API_BASE } from "./env";

export const TRADE_EMAIL = process.env.E2E_TRADE_EMAIL ?? "";
export const TRADE_PASSWORD = process.env.E2E_TRADE_PASSWORD ?? "";
export const CUSTOMER_EMAIL = process.env.E2E_CUSTOMER_EMAIL ?? "";
export const CUSTOMER_PASSWORD = process.env.E2E_CUSTOMER_PASSWORD ?? "";
export const DB_URL = process.env.MTP_DB_URL ?? "";
export const TENANT_SLUG = process.env.E2E_TENANT_SLUG ?? "";

export function tradeCredsConfigured(): boolean {
  return Boolean(TRADE_EMAIL && TRADE_PASSWORD);
}

export function customerCredsConfigured(): boolean {
  return Boolean(CUSTOMER_EMAIL && CUSTOMER_PASSWORD);
}

export function dbConfigured(): boolean {
  return Boolean(DB_URL);
}

export interface ApiTenantContext {
  tenantId: string;
  tenantSlug: string;
  token: string;
}

/** Log in as the trade user via the same endpoint the app uses. */
export async function loginTradeApi(): Promise<ApiTenantContext> {
  const res = await fetch(`${API_BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: TRADE_EMAIL, password: TRADE_PASSWORD }),
  });
  if (!res.ok) throw new Error(`trade API login failed: ${res.status} ${await res.text()}`);
  // The token response embeds everything needed for tenant-scoped calls —
  // no /auth/me or /tenants round-trips (GET /tenants is not even served).
  const body = (await res.json()) as {
    access_token: string;
    tenant_slug: string;
    user: { tenant_id: string };
  };
  return { tenantId: body.user.tenant_id, tenantSlug: body.tenant_slug, token: body.access_token };
}

export async function apiGet(ctx: ApiTenantContext, path: string): Promise<unknown> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${ctx.token}`, "X-Tenant-ID": ctx.tenantId },
  });
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function apiPatch(
  ctx: ApiTenantContext,
  path: string,
  payload: Record<string, unknown>
): Promise<unknown> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${ctx.token}`,
      "X-Tenant-ID": ctx.tenantId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`PATCH ${path} failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// --- Postgres assertions ---------------------------------------------------

let pgPool: import("pg").Pool | null = null;

async function query<T>(sql: string, params: unknown[] = []): Promise<T[]> {
  if (!pgPool) {
    const { Pool } = await import("pg");
    pgPool = new Pool({ connectionString: DB_URL, ssl: { rejectUnauthorized: false } });
  }
  const result = await pgPool.query(sql, params as never[]);
  return result.rows as T[];
}

export async function findContactByEmail(email: string): Promise<Record<string, unknown> | null> {
  const rows = await query<Record<string, unknown>>(
    "SELECT * FROM contacts WHERE email = $1 ORDER BY created_at DESC",
    [email]
  );
  return rows[0] ?? null;
}

export async function findTenantBySlug(slug: string): Promise<Record<string, unknown> | null> {
  const rows = await query<Record<string, unknown>>("SELECT * FROM tenants WHERE slug = $1", [
    slug,
  ]);
  return rows[0] ?? null;
}

export async function findQuotesByTitle(title: string): Promise<Record<string, unknown>[]> {
  return query("SELECT * FROM quotes WHERE title = $1 ORDER BY created_at DESC", [title]);
}

export async function findQuoteRequestsByTitle(
  title: string
): Promise<Record<string, unknown>[]> {
  return query("SELECT * FROM quote_requests WHERE title = $1 ORDER BY created_at DESC", [title]);
}

export async function findPushTokenByData(token: string): Promise<Record<string, unknown> | null> {
  const rows = await query<Record<string, unknown>>("SELECT * FROM push_tokens WHERE token = $1", [
    token,
  ]);
  return rows[0] ?? null;
}

export async function countRows(table: string, where: string, params: unknown[]): Promise<number> {
  const rows = await query(`SELECT count(*)::int AS n FROM ${table} WHERE ${where}`, params);
  return (rows[0] as { n: number }).n;
}

export async function deleteTestData(whereSql: string, params: unknown[]): Promise<void> {
  const scoped = [
    "communications",
    "notifications",
    "push_tokens",
    "invoice_line_items",
    "invoices",
    "appointments",
    "jobs",
    "quote_line_items",
    "quotes",
    "quote_requests",
    "contacts",
  ];
  for (const table of scoped) {
    try {
      await query(`DELETE FROM ${table} WHERE ${whereSql}`, params);
    } catch {
      // Table may not exist in this schema revision — keep cleaning the rest.
    }
  }
}

export async function closeDb() {
  if (pgPool) {
    await pgPool.end();
    pgPool = null;
  }
}
