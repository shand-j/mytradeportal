# Runbook: Deploy RustFS to staging/prod via Railway IaC

## Situation
After PR #318 merged (commit 781b3d6), the `.railway/railway.ts` IaC definition was updated to use RustFS instead of `minio/minio:latest` for object storage. The API service redeployed successfully, but the `minio` service image was not updated because the CI `railway config apply` step fails silently due to a token issue.

## Action
Production deploys now apply the IaC from CI and staging applies it before the
staging verification suites. The steps below are the one-off recovery procedure
for either environment if its CI token is rejected. This requires:
- Railway CLI v5.28+
- Authentication token with Railway project access
- Local machine for browser-auth recovery when a CI token is rejected

### Step 1: Verify prerequisites
```bash
# Check Railway CLI is installed
which railway
railway --version  # should be v5.28+

# Check you're in the correct repo root
pwd  # should end with /mytradeportal
git log -1 --oneline  # should show 781b3d6 or later
```

### Step 2: Authenticate with Railway
```bash
# Login if needed (opens browser for OAuth)
railway login

# Verify authentication works
railway whoami
```

### Step 3: Link to production project
If not already linked, link to the production Railway project:
```bash
cd .railway
railway link
# Select the production project (shand-j/mytradeportal)
# Select "My Trade Portal" or the correct project name
```

**Verify the link:**
```bash
railway list
# Should show your services: postgres, redis, qdrant, minio, api, admin, data-pipeline, landing
```

### Step 4: Preview the IaC changes
Before applying, preview what will change:
```bash
cd .railway
RAILWAY_ENVIRONMENT=production railway config plan
```

Expected diff:
- ✅ `minio` service: image changes from `minio/minio:latest` → `rustfs/rustfs:1.0.6`
- ✅ Volume `/mnt/data` is preserved (no data loss)
- ✅ Environment variables preserved (MINIO_ROOT_USER, MINIO_ROOT_PASSWORD, PORT=9000)
- ⚠️ May show drift corrections for native DB plugins (expected, pre-approved)

### Step 5: Apply the IaC changes
```bash
cd .railway
RAILWAY_ENVIRONMENT=production railway config apply --confirm-destructive
# Review the preview
# Type 'yes' to confirm
```

Repeat the plan/apply commands with `RAILWAY_ENVIRONMENT=staging` for staging.

Expected output:
```
Applying 1 configuration change...
✅ minio: image updated to rustfs/rustfs:1.0.6
✅ Configuration applied successfully
```

### Step 6: Verify deployment
Wait ~2–3 minutes for the new minio container to start, then verify:

**Via Railway CLI:**
```bash
railway service info minio
# Verify: Image: rustfs/rustfs:1.0.6, Status: Running
```

**Via API health check:**
```bash
curl https://api.mytradeportal.co.uk/health
# Should respond: {"status":"ok"}
```

**Via logs:**
```bash
railway logs --service minio --tail 50
# Should show RustFS startup messages (not MinIO)
```

## Rollback (if needed)
If the deployment causes issues, rollback by reverting `.railway/railway.ts` back to MinIO:
```bash
git revert 781b3d6
cd .railway
railway config apply --confirm-destructive
```

Then create an incident issue.

## Gotchas hit in the production rollout (2026-11-19)

1. **RustFS startup now bootstraps a dedicated data path.** Railway still
   execs `start` directly as the container command, so the IaC start command
   must explicitly call RustFS's entrypoint:
   `mkdir -p /mnt/data/rustfs && chown 10001:10001 /mnt/data/rustfs && exec /etc/rustfs/entrypoint.sh`.
   This removes manual `chown` repairs for fresh volumes while avoiding
   root-owned `/mnt/data/lost+found` failures.
2. **Registry policy:** `rustfs/rustfs:1.0.6` is a pinned public Docker Hub
   tag. Railway does not require private registry credentials for this image.
   If a deploy ever reports registry authentication failures, verify no stale
   private-registry override variables were injected in the environment.
3. **Pre-migration objects are orphaned.** RustFS builds its own metadata
   namespace; MinIO's on-disk objects in the volume are NOT served by its
   S3 API (logos/photos 404 until re-uploaded). The old files remain in the
   volume if a salvage is ever needed.
4. **Credential check:** RustFS maps `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`
   at startup; the API signs with `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`.
   Both pairs must hold the same values (production verified aligned).
   **Compare with `railway variables --service <svc> --kv`** — the default
   table view truncates long values, and "aligning" a password to a
   truncated prefix breaks a pair that was already correct (staging,
   2026-11-19: `HeadBucket 403 Forbidden` until the full value was
   restored). The `readiness_probe_failed` warning in the api logs names
   the failing operation.
   The "RUSTFS_ACCESS_KEY is not set" warnings are benign — the entrypoint
   prints them whenever the direct RUSTFS_* vars are unset, even when the
   MINIO_* mapping provides credentials.

## Related
- **PR #318:** Migrate object-storage runtime configs from MinIO image to RustFS
- **Issue:** CI token rejection with Railway CLI v5.28+ (documented in `ci.yml:177-191`)
- **Commit:** 781b3d6
