/**
 * Create a fresh, paid/active tenant + admin for a single E2E test group.
 *
 * Two seeding paths, chosen by environment:
 *
 *   * Local (default): wraps `app.seed_admin_user` inside the API container
 *     via docker compose, then logs in to obtain an access token.
 *   * Remote (E2E_STAGING_SETUP_TOKEN set): creates the tenant through
 *     `POST /tenants` on the live API (staging), gated by the setup token.
 *     The docker path cannot reach a deployed environment.
 *
 * Both paths then resolve the tenant's public config for the 6-digit
 * customer lookup code. This is the foundation of test isolation: every test
 * group gets its own tenant and cannot pollute another group's state.
 *
 * Usage:
 *   const tenant = await createTenant("trade-login");
 */

import { execSync } from "child_process";
import { fileURLToPath } from "url";
import path from "path";

const __filename = fileURLToPath(import.meta.url);
const REPO_ROOT = path.resolve(__filename, "../../..");

const API_BASE = process.env.E2E_API_BASE_URL ?? "http://localhost:8002";

function shellQuote(value) {
  return `'${String(value).replace(/'/g, "'\\''")}'`;
}

function slugify(prefix) {
  const safe = String(prefix)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${safe || "e2e"}-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
}

async function api(path, { method = "GET", body, headers: extraHeaders } = {}) {
  const headers = { Accept: "application/json", ...extraHeaders };
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`${method} ${path} -> ${res.status}: ${text}`);
  }
  const payload = text ? JSON.parse(text) : null;
  return payload;
}

function runSeedScript({ slug, name, adminEmail, adminPassword, adminName }) {
  const cmd = [
    "docker",
    "compose",
    "-f",
    "docker-compose.mobile.yml",
    "run",
    "--rm",
    "-e",
    `SEED_TENANT_SLUG=${shellQuote(slug)}`,
    "-e",
    `SEED_TENANT_NAME=${shellQuote(name)}`,
    "-e",
    `SEED_ADMIN_EMAIL=${shellQuote(adminEmail)}`,
    "-e",
    `SEED_ADMIN_PASSWORD=${shellQuote(adminPassword)}`,
    "-e",
    `SEED_ADMIN_NAME=${shellQuote(adminName)}`,
    "api",
    "python",
    "-m",
    "app.seed_admin_user",
  ].join(" ");
  return execSync(cmd, {
    encoding: "utf-8",
    cwd: REPO_ROOT,
    stdio: "pipe",
    env: {
      ...process.env,
      SUPABASE_URL: "",
      SUPABASE_ANON_KEY: "",
      SUPABASE_SERVICE_ROLE_KEY: "",
    },
  });
}

/**
 * @param {string} [prefix]
 * @returns {Promise<{
 *   slug: string;
 *   code: string;
 *   adminEmail: string;
 *   adminPassword: string;
 *   adminName: string;
 *   token: string;
 *   tenantId: string;
 *   base: string;
 * }>}
 */
/**
 * Create the tenant on a deployed API via `POST /tenants` (setup-token
 * gated). Used for the staging regression run, where the docker seed path
 * cannot reach the database. The admin user is created atomically with the
 * tenant, so it can log in immediately afterwards.
 */
async function seedRemote({ slug, name, adminEmail, adminPassword, adminName }) {
  await api("/tenants", {
    method: "POST",
    headers: { "X-Setup-Token": process.env.E2E_STAGING_SETUP_TOKEN },
    body: { slug, name, admin_email: adminEmail, admin_password: adminPassword, admin_name: adminName },
  });
}

export async function createTenant(prefix = "e2e") {
  const slug = slugify(prefix);
  const adminEmail = `owner-${slug}@e2e-regression.trade`;
  const adminPassword = "E2E-Password-1";
  const adminName = "E2E Trade Owner";
  const remote = Boolean(process.env.E2E_STAGING_SETUP_TOKEN);

  if (remote) {
    await seedRemote({
      slug,
      name: `E2E ${prefix} tenant`,
      adminEmail,
      adminPassword,
      adminName,
    });
  } else {
    runSeedScript({
      slug,
      name: `E2E ${prefix} tenant`,
      adminEmail,
      adminPassword,
      adminName,
    });
  }

  // Log in to obtain the token and tenant id. The backend may need a moment to
  // index the new user, and the login endpoint is rate-limited, so retry with
  // a conservative backoff.
  let auth;
  let lastError;
  for (let attempt = 0; attempt < 15; attempt++) {
    try {
      auth = await api("/auth/token", {
        method: "POST",
        body: { email: adminEmail, password: adminPassword, tenant_slug: slug },
      });
      break;
    } catch (err) {
      lastError = err;
      const delay =
        err instanceof Error && err.message.includes("429") ? 15000 : 1000;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  if (!auth) {
    throw new Error(`Could not authenticate seeded admin: ${lastError?.message}`);
  }

  // The backend login endpoint is rate-limited (5/min). Because every test
  // group creates a fresh tenant and immediately logs in, pause here to keep
  // the suite under the limit. Staging runs with rate limiting disabled, so
  // the pause is dead time there.
  if (!remote) {
    await new Promise((resolve) => setTimeout(resolve, 15000));
  }

  // Fetch public config for the 6-digit customer lookup code.
  const publicConfig = await api(`/businesses/${slug}/public-config`);

  return {
    slug,
    code: publicConfig.code ?? slug,
    adminEmail,
    adminPassword,
    token: auth.access_token,
    tenantId: auth.user.tenant_id,
    adminName,
    base: API_BASE,
  };
}
