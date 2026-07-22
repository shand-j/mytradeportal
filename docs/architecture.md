# Architecture

My Trade Portal V2 is split into three conceptual layers. The current codebase
implements the **Intelligence** and **Operations** layers; the **Customer
Experience** layer is planned.

```
┌─────────────────────────────────────────────────────────────┐
│            Layer 1: Customer Experience (planned)           │
│  White-label PWA · Voice AI · Web chatbot · WhatsApp/SMS    │
├─────────────────────────────────────────────────────────────┤
│              Layer 2: Intelligence (partial)                │
│  RAG Quote Engine · Cost database · LLM router              │
├─────────────────────────────────────────────────────────────┤
│              Layer 3: Operations (implemented)              │
│  CRM · Quotes · Jobs · Appointments · Invoices · Payments   │
└─────────────────────────────────────────────────────────────┘
```

See [`mtp_v2_architecture.png`](../mtp_v2_architecture.png) for the full system
diagram and [`mtp_v2_product_spec.md`](../mtp_v2_product_spec.md) for the
long-form product vision.

## Service layout

The local stack is defined in `docker-compose.yml`:

- **FastAPI API** — async Python backend, auto-generated OpenAPI docs.
- **Django Admin** — staff interface; uses unmanaged models mirroring the
  FastAPI schema.
- **OpenConstructionERP (ocerp)** — internal estimation microservice for Bill
  of Quantities generation and cost lookups; communicates with the API only via
  HTTP to keep any AGPL estimation code out of the proprietary codebase.
- **PostgreSQL** — single operational database with tenant-scoped tables.
- **Qdrant** — vector database for semantic search over cost items.
- **Redis** — cache and future task broker.
- **MinIO** — S3-compatible object storage for uploads.
- **Mailpit** — captures outbound email during development.

## Multi-tenancy

Tenants represent trade businesses. Isolation is enforced at the application
layer:

1. Every API request must include the header `X-Tenant-ID: <tenant-uuid>`.
2. FastAPI dependencies load the tenant and set it in the PostgreSQL session as
   `app.current_tenant`.
3. Row-Level Security (RLS) policies ensure queries only return rows where
   `tenant_id` matches the current session value.

```sql
CREATE POLICY tenant_isolation ON quotes
    USING (tenant_id = current_setting('app.current_tenant')::UUID);
```

This keeps the operational overhead low while giving each business its own data
boundary.

## Data model

Core entities are managed by FastAPI/SQLAlchemy and mirrored read-only in Django:

| Entity | Purpose |
|---|---|
| `Tenant` | Trade business; isolation boundary |
| `Contact` | Customer or lead |
| `User` | Staff member belonging to a tenant |
| `Quote` / `QuoteLineItem` | Price estimate |
| `Job` | Work order created from a quote or directly |
| `Appointment` | Scheduled calendar event for a job |
| `Invoice` / `InvoiceLineItem` | Bill for completed work |
| `Payment` | Payment record (Paddle) |
| `CostItem` | Shared cost database entry |
| `Communication` | Logged email/SMS/call/chat |
| `AuditLog` | Immutable audit trail |

The vector search schema lives in Qdrant in the `cost_items` collection (768 dims
with the default Ollama embedding model).
