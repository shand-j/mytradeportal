# Custom Domains Runbook

Configure custom domains for the My Trade Portal V2 production stack on Railway.

**Scope:** FastAPI API (`api`), React back-office (`web`), Django admin (`admin`), and MinIO (`minio`). OCERP, Qdrant, Redis, and Postgres are only reached internally through Railway private networking and do not need public domains.

**Current production state** (for reference):

- Railway Project: `MyTradePortal` (`30feaeee-9464-41ac-9b17-d07ae4cfcd09`)
- Environment: `production`
- Current service domains (use `railway service list --json` to get the exact values for your environment):
  - API: `https://<api-domain>`
  - Web: `https://<web-domain>`
  - Admin: `https://<admin-domain>`
- IaC target region: `europe-west4-drams3a` (Amsterdam). All services are deployed in this region.

---

## Why custom domains matter

- **Brand trust:** Customers see `app.yourcompany.co.uk` rather than a `*.up.railway.app` URL.
- **Multi-tenancy:** The back-office UI resolves tenants by subdomain. Custom domains with a wildcard DNS record allow per-tenant URLs such as `acme.app.yourcompany.co.uk`.
- **Cookie security:** The API sets the `session` cookie with `Secure=true`. Custom domains on HTTPS keep cookie scoping predictable and prevent cross-domain leakage.
- **CORS/CSRF:** `ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, and `VITE_API_BASE_URL` must all be updated to the final public domains.

---

## Recommended domain layout

Use one apex domain and per-service subdomains. This is the easiest pattern to maintain in Railway and supports wildcard tenant subdomains on the `web` domain.

| Service | Public domain | Purpose |
|---|---|---|
| `web` | `app.example.com` | React back-office SPA |
| `api` | `api.example.com` | FastAPI backend |
| `admin` | `admin.example.com` | Django admin panel |
| `minio` | `storage.example.com` | S3-compatible object storage |

For multi-tenant per-business URLs, use a wildcard under the web domain:

| Tenant slug | Resolved URL |
|---|---|
| `acme` | `acme.app.example.com` |
| `sparky` | `sparky.app.example.com` |

You must add a wildcard DNS record (`*.app.example.com`) for this to work.

---

## Before you start

You need:

1. A domain you control and access to its DNS records.
2. The Railway CLI installed and linked to the `MyTradePortal` project:

   ```bash
   railway login
   cd .railway && railway link
   ```

3. The latest IaC applied so service references exist:

   ```bash
   railway config plan
   railway config apply
   ```

4. The current production smoke-test URLs noted from GitHub Actions secrets (`E2E_BASE_URL`, `E2E_ADMIN_BASE_URL`).

---

## Step 1: Register custom domains in Railway

Railway IaC cannot register custom domains (`.railway/railway.ts` comment at line 17). Add them through the dashboard.

1. Open the Railway dashboard and select the `MyTradePortal` project → `production` environment.
2. For each service below, go to **Settings → Public Networking → + Custom Domain**:
   - `web` → `app.example.com` (target port **80**, or **443** if Railway asks for HTTPS)
   - `api` → `api.example.com` (target port **8000**)
   - `admin` → `admin.example.com` (target port **8001**)
   - `minio` → `storage.example.com` (target port **9000**)
3. Railway will display the DNS records required for each. Typically these are **CNAME** records pointing to a Railway edge endpoint.

**Example DNS records**

| Type | Name | Value |
|---|---|---|
| CNAME | `api` | `<api-domain>` (or the Railway-provided target) |
| CNAME | `admin` | `<admin-domain>` (or the Railway-provided target) |
| CNAME | `app` | `<web-domain>` (or the Railway-provided target) |
| CNAME | `storage` | `<minio-domain>` (or the Railway-provided target) |
| CNAME | `*.app` | `<web-domain>` (or the Railway-provided target) |

> **Tip:** Use the exact CNAME targets Railway gives you, not the old `*.up.railway.app` URLs from this runbook. The examples above are the current service domains; Railway may rewrite them through its edge.

4. Wait for DNS propagation (usually a few minutes, up to an hour). Railway will show a **Verified** status for each domain.

---

## Step 2: Pull the updated domain references into IaC

After the domains are verified, pull the current Railway configuration so the IaC file contains the new `RAILWAY_PUBLIC_DOMAIN` references.

```bash
cd .railway
railway config pull
```

Review the diff carefully. The pull should update the public-domain interpolation variables; it should not overwrite secrets marked with `preserve()`.

---

## Step 3: Update environment variables

Custom domains change the public URLs that the services expose to each other and to browsers. Update the following Railway variables.

### `api` service

| Variable | New value | Why |
|---|---|---|
| `ALLOWED_ORIGINS` | `https://app.example.com` | CORS: the React SPA must be allowed to call the API. |
| `MINIO_ENDPOINT` | `storage.example.com` | Presigned upload URLs returned by the API must be reachable by the browser. |

Set them with the Railway CLI:

```bash
railway variable set ALLOWED_ORIGINS="https://app.example.com" --service api --environment production
railway variable set MINIO_ENDPOINT="storage.example.com" --service api --environment production
```

### `web` service

| Variable | New value | Why |
|---|---|---|
| `VITE_API_BASE_URL` | `https://api.example.com` | Baked into the Vite bundle at Docker build time. |

```bash
railway variable set VITE_API_BASE_URL="https://api.example.com" --service web --environment production
```

### `admin` service

| Variable | New value | Why |
|---|---|---|
| `ALLOWED_HOSTS` | `admin.example.com,<admin-domain>,localhost,127.0.0.1` | Django rejects hostnames not in this list. Keep the old Railway domain as a fallback during cutover. |
| `CSRF_TRUSTED_ORIGINS` | `https://admin.example.com` | Required for Django admin POST requests. |

```bash
railway variable set ALLOWED_HOSTS="admin.example.com,<admin-domain>,localhost,127.0.0.1" --service admin --environment production
railway variable set CSRF_TRUSTED_ORIGINS="https://admin.example.com" --service admin --environment production
```

### `minio` service

No new variables are required, but verify the bucket (`mtp-uploads`) exists and the credentials match `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`.

---

## Step 4: Redeploy affected services

Railway will redeploy automatically when variables change. Trigger a manual redeploy if you prefer to control timing:

```bash
railway redeploy --service api --environment production
railway redeploy --service web --environment production
railway redeploy --service admin --environment production
```

The `web` service must be redeployed last because `VITE_API_BASE_URL` is baked into the bundle at build time. If you update it first, the bundle will still point to the old API domain until the next deploy.

---

## Step 5: Verify

### DNS and TLS

```bash
# DNS resolution
host api.example.com
host app.example.com
host admin.example.com
host storage.example.com
host acme.app.example.com   # wildcard tenant subdomain

# TLS and redirect
# HTTPS should return a valid certificate.
```

### Health checks

```bash
curl -I https://api.example.com/health
curl -I https://admin.example.com/health
curl -I https://app.example.com/
curl -I https://storage.example.com/
```

All should return `200 OK` or `302` (admin login redirect).

### End-to-end application check

1. Open `https://app.example.com/login`.
2. Enter a tenant slug and log in.
3. Create a test quote and confirm the BoQ/AI generation path succeeds (calls `https://api.example.com`).
4. Upload a file in the quote or job view and confirm the presigned URL points to `https://storage.example.com`.
5. Log in to `https://admin.example.com/admin/` with the configured Django superuser and verify the Django admin loads without CSRF errors.

---

## Step 6: Update GitHub Actions secrets

The smoke-test workflow (`.github/workflows/smoke-production.yml`) uses production URLs stored in the `MyTradePortal/Production` environment secrets.

Update these secrets in the GitHub repository:

| Secret | New value |
|---|---|
| `E2E_BASE_URL` | `https://app.example.com` |
| `E2E_ADMIN_BASE_URL` | `https://admin.example.com` |

You do not need to change `DATABASE_URL` unless the database itself moved; custom domains do not affect the Postgres connection string.

Re-run the production smoke test after the secrets are updated:

```bash
# GitHub CLI example
gh workflow run smoke-production.yml --repo shand-j/mytradeportal
```

Or trigger it from the **Actions → Production Smoke Test → Run workflow** page.

---

## Multi-tenancy considerations

The web app resolves tenants by subdomain. With custom domains, you must support the wildcard pattern `*.app.example.com`.

### Required DNS configuration

Add a wildcard CNAME:

| Type | Name | Value |
|---|---|---|
| CNAME | `*.app` | Same target as the `app` record |

### How the app resolves the tenant

1. Browser requests `https://acme.app.example.com`.
2. The React SPA reads `window.location.hostname` and sends `X-Tenant-ID: acme` (or the resolved tenant UUID) on every API request.
3. The FastAPI backend validates the JWT `tenant_id` claim and sets the Postgres `app.current_tenant` setting so RLS policies enforce isolation.

If a tenant subdomain does not match a known tenant slug, the user is redirected to the root login page.

### API-only tenants

Tenants can also be accessed by sending the `X-Tenant-ID` header directly to `https://api.example.com`. This is how programmatic integrations and the mobile PWA will call the API. The custom domain does not change this behaviour.

---

## Security checklist

Before considering the cutover complete, verify:

- [ ] All four public services are served over HTTPS.
- [ ] `api.example.com` `ALLOWED_ORIGINS` does not include `*` and only lists the `web` domain.
- [ ] `admin.example.com` `CSRF_TRUSTED_ORIGINS` is set to `https://admin.example.com`.
- [ ] `AUTH_COOKIE_SECURE` remains `true` in production (default).
- [ ] The old `*.up.railway.app` URLs still work or are removed intentionally. If you keep them, ensure `ALLOWED_HOSTS` and `ALLOWED_ORIGINS` include them only during the transition window.
- [ ] `MINIO_USE_SSL=true` and the presigned URLs use `https://storage.example.com`.
- [ ] Wildcard `*.app.example.com` DNS is configured for tenant subdomain resolution.
- [ ] `SETUP_TOKEN` and `AUTH_SECRET_KEY` are still strong, uncommitted values.
- [ ] The production smoke test passes with the new `E2E_BASE_URL` and `E2E_ADMIN_BASE_URL` secrets.

---

## Rollback plan

If the custom domain cutover breaks production, roll back quickly without losing data.

1. Revert the environment variables to the previous Railway service domains:

   ```bash
   railway variable set ALLOWED_ORIGINS="https://<api-domain>" --service api --environment production
   railway variable set MINIO_ENDPOINT="<minio-domain>" --service api --environment production
   railway variable set VITE_API_BASE_URL="https://<api-domain>" --service web --environment production
   railway variable set ALLOWED_HOSTS="<admin-domain>,localhost,127.0.0.1" --service admin --environment production
   railway variable set CSRF_TRUSTED_ORIGINS="https://<admin-domain>" --service admin --environment production
   ```

2. Redeploy `api`, `web`, and `admin`.
3. Update the GitHub Actions secrets back to the old URLs.
4. Re-run the production smoke test.

The database, Qdrant, and MinIO data are not affected by domain changes.

---

## Troubleshooting

### Domain verification hangs in Railway

- Confirm the DNS record is a **CNAME**, not an A record pointing to an IP.
- Check for a CAA record that restricts certificate issuance to a non-Railway CA. Remove or add `0 issue "letsencrypt.org"`.
- Wait for full DNS propagation; use `dig +trace app.example.com` to inspect the chain.

### API requests fail with CORS errors

- Confirm `ALLOWED_ORIGINS` on the `api` service is exactly `https://app.example.com` (no trailing slash, no `http://`).
- Check that the browser is calling `https://api.example.com`, not the old Railway domain.
- Verify the `web` service was redeployed after `VITE_API_BASE_URL` changed.

### Admin login fails with CSRF or `DisallowedHost`

- Confirm `ALLOWED_HOSTS` includes `admin.example.com`.
- Confirm `CSRF_TRUSTED_ORIGINS` is `https://admin.example.com`.
- If accessing via an old URL, add it to `ALLOWED_HOSTS` temporarily.

### File uploads fail or return 403

- Confirm `MINIO_ENDPOINT` is `storage.example.com` (no `https://` prefix) and `MINIO_USE_SSL=true`.
- Confirm the browser can reach `https://storage.example.com`.
- Confirm the `mtp-uploads` bucket exists and credentials match.

### Tenant subdomain returns 404

- Confirm the wildcard `*.app.example.com` CNAME is present and propagated.
- Confirm the tenant slug exists in the database (`tenants` table).
- Check the Railway domain target for `web` is correct; the wildcard and apex `app` records should point to the same place.

### Smoke test still points to old URL

- Check the `E2E_BASE_URL` and `E2E_ADMIN_BASE_URL` secrets in the `MyTradePortal/Production` GitHub environment.
- Re-run the workflow; GitHub Actions reads secrets at runtime, not at workflow file commit time.

---

## Related documents

- [`docs/deployment.md`](deployment.md) — full production deployment and IaC instructions
- [`.railway/railway.ts`](../.railway/railway.ts) — Railway Infrastructure as Code
- [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) — CI/CD pipeline
- [`.github/workflows/smoke-production.yml`](../.github/workflows/smoke-production.yml) — production smoke test
- [`docs/soc2-controls.md`](soc2-controls.md) — security and compliance controls
