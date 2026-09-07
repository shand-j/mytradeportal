# API overview

The FastAPI backend exposes a REST API. OpenAPI documentation is available
interactively at `/docs` and as JSON at `/openapi.json`.

## Authentication and tenant context

The back-office UI authenticates staff users via the `/auth` endpoints. A
successful login sets an HTTP-only `session` cookie containing a signed JWT.
Subsequent browser requests automatically include this cookie.

```http
POST /auth/login
Content-Type: application/json

{
  "tenant_slug": "demo",
  "email": "you@example.com",
  "password": "<the password you set via SEED_ADMIN_PASSWORD>"
}
```

All operational endpoints also require the tenant header:

```http
X-Tenant-ID: <tenant-uuid>
```

Create a tenant via `POST /tenants` to obtain an ID, or use `python -m
app.seed_admin_user` (with `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` set) to
bootstrap a local-dev tenant and admin user.

Webhook endpoints (`/webhooks/*`) do **not** use the tenant header; they identify
the tenant from the provider payload.

## Endpoints

### Auth

| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | Authenticate with tenant slug, email and password; sets session cookie |
| POST | `/auth/logout` | Clear the session cookie |
| GET | `/auth/me` | Return the currently authenticated user |

### Users

| Method | Path | Description |
|---|---|---|
| GET | `/users` | List staff users for the current tenant |
| POST | `/users` | Create a staff user (admin only) |
| GET | `/users/{id}` | Get a staff user |
| PATCH | `/users/{id}` | Update a staff user (admin or manager) |
| DELETE | `/users/{id}` | Delete a staff user (admin only) |

### Health

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Service health check |

### Tenants

| Method | Path | Description |
|---|---|---|
| POST | `/tenants` | Create a new trade business |

### Contacts

| Method | Path | Description |
|---|---|---|
| GET | `/contacts` | List contacts |
| POST | `/contacts` | Create a contact |
| GET | `/contacts/{id}` | Get a contact |
| PUT | `/contacts/{id}` | Update a contact |
| DELETE | `/contacts/{id}` | Delete a contact |

### Quotes

| Method | Path | Description |
|---|---|---|
| GET | `/quotes` | List quotes |
| POST | `/quotes` | Create a manual quote |
| GET | `/quotes/{id}` | Get a quote |
| POST | `/quotes/{id}/approve` | Approve or reject a quote |
| POST | `/quotes/generate` | **Generate a draft quote from a job description** |
| POST | `/quotes/generate-boq` | Generate a draft quote using the OpenConstructionERP BoQ engine |
| POST | `/quotes/{id}/convert-to-invoice` | Convert a quote to an invoice |

### Jobs

| Method | Path | Description |
|---|---|---|
| GET | `/jobs` | List jobs |
| POST | `/jobs` | Create a job |
| GET | `/jobs/{id}` | Get a job |
| PUT | `/jobs/{id}` | Update a job |
| DELETE | `/jobs/{id}` | Delete a job |

### Appointments

| Method | Path | Description |
|---|---|---|
| GET | `/appointments` | List appointments |
| POST | `/appointments` | Create an appointment |
| GET | `/appointments/{id}` | Get an appointment |
| PUT | `/appointments/{id}` | Update an appointment |
| DELETE | `/appointments/{id}` | Delete an appointment |

### Invoices

| Method | Path | Description |
|---|---|---|
| GET | `/invoices` | List invoices |
| POST | `/invoices` | Create an invoice |
| GET | `/invoices/{id}` | Get an invoice |
| POST | `/invoices/{id}/issue` | Mark an invoice as issued |

### Payments

| Method | Path | Description |
|---|---|---|
| POST | `/payments/checkout` | Create a Paddle checkout for an invoice |
| GET | `/payments/invoice/{invoice_id}` | List payments for an invoice |

### Webhooks

| Method | Path | Description |
|---|---|---|
| POST | `/webhooks/paddle` | Paddle transaction webhooks |

## Example: generate a quote

```bash
# Create tenant
TENANT=$(curl -s -X POST http://localhost:8000/tenants \
  -H "Content-Type: application/json" \
  -d '{"slug":"demo","name":"Demo Electrical"}' | jq -r '.id')

# Generate quote
curl -s -X POST http://localhost:8000/quotes/generate \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT" \
  -d '{
    "description": "Upgrade consumer unit and add two double sockets",
    "customer_name": "Bob",
    "customer_email": "bob@example.com",
    "property_type": "House"
  }' | jq
```

## Example: generate a Bill of Quantities quote

```bash
# Generate a detailed BoQ-driven quote via the OpenConstructionERP microservice
curl -s -X POST http://localhost:8000/quotes/generate-boq \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT" \
  -d '{
    "description": "Full rewire of a 3 bedroom house including consumer unit upgrade",
    "customer_name": "Alice",
    "customer_email": "alice@example.com",
    "property_type": "House"
  }' | jq
```

## Error responses

The API returns standard HTTP status codes:

- `400` — invalid request data or tenant mismatch
- `404` — resource not found
- `503` — AI provider unavailable (e.g. OpenAI API unreachable or quota exceeded)
