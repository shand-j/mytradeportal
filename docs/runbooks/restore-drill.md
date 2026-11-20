# Runbook: isolated production restore drill

## Gate

This runbook provides evidence for beta gate G4. It is not complete until a
human has selected and restored a real production restore point into an
isolated, access-controlled estate, and recorded actual RPO and RTO.
Code inspection or a successful application startup is not proof.

Targets:

- **RPO:** restored data must be no more than 24 hours older than the incident
  time / drill start.
- **RTO:** elapsed time from drill start to all validation passing must be no
  more than 60 minutes.

**Never overwrite production.** The isolated database, object-storage endpoint,
Qdrant endpoint, API origin, DNS, credentials, and API keys must be separate
from production. Do not issue live webhook, payment, email, SMS, or push traffic
from the drill estate.

## 1. Preparation

Record in the evidence ticket before starting:

- Incident simulation time (`T0`)
- Production restore-point timestamp and provider/snapshot ID
- Restore-point age: `T0 - restore_point_timestamp`
- Isolated environment owner and access-control review
- PostgreSQL, RustFS, Qdrant, API, and tenant/test identities
- Rollback owner and teardown deadline

Select the newest production restore point that is safe and demonstrably
consistent. Prefer provider snapshots over ad-hoc dumps. Record whether
PostgreSQL, object storage, and Qdrant restore points belong to the same
close-of-snapshot window.

Create isolated credentials and dependencies. Do not copy production secret
values into this repository or into shell history. Export them only in the
human runner's process environment.

```bash
export RESTORE_API_BASE_URL="https://restore-api.example.invalid"
export RESTORE_DATABASE_URL="postgresql://<isolated-app-role>:<secret>@<isolated-host>/<database>"
export RESTORE_QDRANT_URL="https://restore-qdrant.example.invalid"
export RESTORE_AUTH_TOKEN="<isolated-or-restored-test-user-token>"
export RESTORE_TENANT_ID="<test-tenant-uuid>"
export RESTORE_BUSINESS_SLUG="<test-business-slug>"
```

Use an isolated API role that is `NOSUPERUSER NOBYPASSRLS`. RLS validation
requires no cross-tenant bypass.

## 2. PostgreSQL restore

Start a timer at `T0`. Restore into a fresh isolated database instance and
run the normal schema reconciliation, but do not run migrations that invent or
write data:

```bash
python scripts/init_db.py
```

Capture restore-point metadata and elapsed time. Verify PostgreSQL health,
schema, RLS, and tenant isolation with:

```bash
python scripts/validate_restore.py \
  --api-base "$RESTORE_API_BASE_URL" \
  --database-url "$RESTORE_DATABASE_URL" \
  --tenant-a "$RESTORE_TENANT_ID" \
  --evidence-json restore-validation.json
```

The validator rejects a superuser/BYPASSRLS role, missing tables or columns,
missing tenant RLS/FORCE policies, and a `/ready` status that is not `ready`.
It also records table counts and per-table checksums.

For offboarding-reanonymisation proof, identify all restored tenants known to
have been offboarded before the restore point and run the offboard transaction
again only against the isolated copy. This re-applies PII anonymisation and
token revocation. Never do this in production. Record tenant slug/ID, original
offboarding time, restoration time, and verification that no staff/customer
PII remains.

## 3. RustFS/object-storage restore

Restore the production object-storage volume or snapshot into a fresh isolated
RustFS service. Keep the isolated S3 endpoint private and aligned credentials
separate from production.

Verify the bucket, object inventory, and representative retrieval. The API
must serve content through `/files/download`, with an auth header and tenant
prefix enforcement. The public logo endpoint and public quote/invoice
document endpoint must only be exercised with isolated test data.

Add evidence:

- Bucket and object counts
- Restore-point timestamp/provider ID
- Representative media/logo/document object keys and SHA-256 values
- A cross-tenant file-key request returning 404

Example:

```bash
python scripts/validate_restore.py \
  --api-base "$RESTORE_API_BASE_URL" \
  --database-url "$RESTORE_DATABASE_URL" \
  --tenant-id "$RESTORE_TENANT_ID" \
  --tenant-a "$RESTORE_TENANT_ID" \
  --auth-token "$RESTORE_AUTH_TOKEN" \
  --business-slug "$RESTORE_BUSINESS_SLUG" \
  --file-key "tenants/$RESTORE_TENANT_ID/<representative-object-id>/<safe-name>" \
  --document-url "https://<isolated-public-origin>/public/<kind>/<isolated-token>" \
  --evidence-json restore-validation.json
```

Do not log object contents or credentials. Hashes and key prefixes are sufficient.

## 4. Qdrant restore

Restore the newest Qdrant snapshot into an isolated instance, or document and
execute the authoritative rebuild from `scripts/seed_cost_items.py` and
`scripts/seed_knowledge.py`.

If a snapshot is used:

```bash
# Use provider/API instructions appropriate to the isolated deployment.
# Never restore a Qdrant snapshot over a production collection.
```

If rebuilding:

```bash
python scripts/seed_cost_items.py
python scripts/seed_knowledge.py
```

The environment must point only at the isolated Qdrant service. Validate the
expected collections and point counts:

```bash
python scripts/validate_restore.py \
  --api-base "$RESTORE_API_BASE_URL" \
  --qdrant-url "$RESTORE_QDRANT_URL" \
  --qdrant-collection "<cost-items-collection>" \
  --qdrant-collection "<knowledge-collection>"
```

Add a direct representative retrieval result and note whether snapshot restore
or authoritative rebuild was used.

## 5. Representative application reads

Start the API against the recovered PostgreSQL, RustFS, and Qdrant endpoints.
No external providers or write paths may be enabled.

Select non-sensitive restored test IDs. Validate:

- `/ready` returns `status=ready`
- Quote list/detail
- Job list/detail
- Invoice list/detail
- A quote → job → invoice relationship
- Tenant logo
- Authenticated media retrieval
- Public quote/invoice document retrieval
- Object checksum and API response checksum
- Tenants remain isolated through both API auth and database RLS
- Qdrant collection exists and has expected point counts

```bash
python scripts/validate_restore.py \
  --api-base "$RESTORE_API_BASE_URL" \
  --database-url "$RESTORE_DATABASE_URL" \
  --tenant-id "$RESTORE_TENANT_ID" \
  --tenant-a "$RESTORE_TENANT_ID" \
  --tenant-b "<second-isolated-tenant-uuid>" \
  --auth-token "$RESTORE_AUTH_TOKEN" \
  --quote-id "<representative-quote-id>" \
  --job-id "<representative-job-id>" \
  --invoice-id "<representative-invoice-id>" \
  --file-key "tenants/$RESTORE_TENANT_ID/<representative-object-id>/<safe-name>" \
  --business-slug "$RESTORE_BUSINESS_SLUG" \
  --document-url "https://<isolated-public-origin>/public/<kind>/<isolated-token>" \
  --qdrant-url "$RESTORE_QDRANT_URL" \
  --qdrant-collection "<cost-items-collection>" \
  --qdrant-collection "<knowledge-collection>" \
  --evidence-json restore-validation.json
```

## 6. Evidence

Store only sanitized evidence in the incident/ticket system:

- Restore start/end timestamps
- Restore-point timestamps and provider IDs
- RPO formula/result
- RTO formula/result
- `/ready` and dependency status
- Schema/table/column and RLS result
- Table counts/checksums
- Tenant isolation result
- Representative quote/job/invoice IDs (prefer synthetic IDs)
- Media/logo/document key prefixes and SHA-256 values
- Qdrant collection names and point counts
- Offboarding re-anonymisation result
- Failure, remediation, and teardown notes

Do not attach database dumps, object contents, tokens, PII, full URLs containing
document tokens, secret environment values, or raw provider credentials.

## 7. Failure handling

Stop the drill and preserve evidence if any of these occur:

- No restore point exists or it is older than 24 hours
- Restore is not isolated or could write production
- PostgreSQL schema or RLS validation fails
- Tenant isolation fails
- Object storage or representative content is missing
- Qdrant snapshot cannot restore and authoritative rebuild is unavailable
- `/ready` cannot reach every hard dependency
- Re-anonymisation of offboarded tenants fails
- Measured RTO exceeds 60 minutes

File blockers for missing backup or recovery paths. Beta remains **NO-GO**
until RPO and RTO targets are proven by live human evidence.

## 8. Isolated-estate teardown

After evidence review:

- Revoke all isolated API, database, object-storage, and Qdrant credentials
- Disable and delete temporary DNS/origins
- Delete the isolated database, volume/snapshot, and Qdrant collections
- Purge drill logs containing sensitive request IDs or URLs
- Remove local environment exports and evidence files containing secrets
- Confirm production resources were untouched
- Record teardown timestamp and owner
