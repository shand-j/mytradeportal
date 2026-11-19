# Runbook: Deploy RustFS to staging/prod via Railway IaC

## Situation
After PR #318 merged (commit 781b3d6), the `.railway/railway.ts` IaC definition was updated to use `rustfs/rustfs:latest` instead of `minio/minio:latest` for object storage. The API service redeployed successfully, but the `minio` service image was not updated because the CI `railway config apply` step fails silently due to a token issue.

## Action
Deploy the IaC changes manually using the Railway CLI. This requires:
- Railway CLI v5.28+
- Authentication token with Railway project access
- Local machine (the CI environment has a known token rejection issue)

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
railway config plan
```

Expected diff:
- ✅ `minio` service: image changes from `minio/minio:latest` → `rustfs/rustfs:latest`
- ✅ Volume `/mnt/data` is preserved (no data loss)
- ✅ Environment variables preserved (MINIO_ROOT_USER, MINIO_ROOT_PASSWORD, PORT=9000)
- ⚠️ May show drift corrections for native DB plugins (expected, pre-approved)

### Step 5: Apply the IaC changes
```bash
cd .railway
railway config apply --confirm-destructive
# Review the preview
# Type 'yes' to confirm
```

Expected output:
```
Applying 1 configuration change...
✅ minio: image updated to rustfs/rustfs:latest
✅ Configuration applied successfully
```

### Step 6: Verify deployment
Wait ~2–3 minutes for the new minio container to start, then verify:

**Via Railway CLI:**
```bash
railway service info minio
# Verify: Image: rustfs/rustfs:latest, Status: Running
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

1. **Never set `start` for the RustFS service.** Railway execs the IaC
   `start` value directly as the container command — unlike
   docker-compose's `command:`, it is NOT passed to the image entrypoint.
   `start: "/mnt/data"` tried to exec a directory and failed the deploy with
   "We don't have permission to execute your start command". Leave `start`
   unset and point the entrypoint at the volume via `RUSTFS_VOLUMES`
   (resolved by `/etc/rustfs/entrypoint.sh`).
2. **Volume ownership: MinIO ran as root, RustFS runs as uid 10001
   (`rustfs`).** The pre-existing volume mountpoint and files are
   root-owned, so the first RustFS boot dies with
   `[FATAL] Server runtime failed: File access denied` (a subdirectory
   under the mount fails the same way). Fix once by temporarily pointing the
   service at a root image with a one-shot chown, then reverting:
   - `source: image("alpine:latest")`,
     `start: 'sh -c "chown -R 10001:10001 /mnt/data && echo CHOWN-DONE && sleep 600"'`
     → `railway config apply`, wait for `CHOWN-DONE` in the logs
     (`railway logs --deployment <id>` — the service-level log tail lags and
     interleaves old deployments; query by deployment id).
   - Revert to the RustFS block → apply again. Deploy goes green.
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
