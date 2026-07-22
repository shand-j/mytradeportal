# AI Quote Engine

The RAG (Retrieval-Augmented Generation) Quote Engine turns a plain-language job
description into a draft quote grounded in real cost data.

## How it works

1. **Embed the query** — the job description is sent to an embedding model.
2. **Vector search** — Qdrant returns the most similar cost items, filtered by
   trade (`electrical`) and region (`UK`).
3. **LLM generation** — a local or remote chat model receives the retrieved
   items, business pricing rules and the job description, then returns a JSON
   line-item list.
4. **Validation** — the response is mapped back to retrieved items, sanity
   checked and scored for confidence.
5. **Quote creation** — a draft `Quote` with line items is saved in PostgreSQL.

## Cost database

The cost database has two sources:

- **Seed data** — a small curated set of UK electrical items (consumer units,
  sockets, EV chargers, EICRs, etc.) in
  `services/api/app/data/uk_electrical_cost_items.json`.
- **DDC CWICR UK** — ~4,200 electrical scope-of-work rows from the
  OpenConstructionERP project, downloaded and ingested by
  `services/api/app/ingest_ddc_uk.py`.

Both sources are stored in PostgreSQL and embedded into Qdrant.

## Configuration

Relevant environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_API_BASE` | `http://host.docker.internal:11434` | Ollama endpoint (inside Docker) |
| `EMBEDDING_MODEL` | `ollama/nomic-embed-text` | Embedding model passed to LiteLLM |
| `LLM_MODEL` | `ollama/gpt-oss:latest` | Chat model passed to LiteLLM |
| `OPENAI_API_KEY` | *(empty)* | Required only if using OpenAI models |
| `QDRANT_URL` | `http://localhost:6333` | Vector database |
| `QDRANT_COLLECTION_NAME` | `cost_items` | Qdrant collection |
| `EMBEDDING_DIMENSIONS` | *(auto)* | Override vector size (768/1536/3072) |

To switch back to OpenAI:

```bash
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
LLM_MODEL=gpt-4o-mini
```

## Ingestion scripts

```bash
# Seed curated items
cd services/api
python -m app.seed_cost_items

# Ingest DDC CWICR UK data (~4k items)
python -m app.ingest_ddc_uk
```

The collection is recreated automatically if the configured embedding dimension
changes, so you can switch models without manual Qdrant administration.

## OpenConstructionERP integration

For complex jobs the platform can generate a detailed Bill of Quantities (BoQ)
via a dedicated microservice:

- `services/ocerp/` — FastAPI microservice implementing the OpenConstructionERP
  API contract (`/ocerp/v1/boq/generate`, `/ocerp/v1/price/lookup`,
  `/ocerp/v1/standards/list`).
- `services/api/app/clients/ocerp.py` — HTTP client used by the main API to call
  the microservice.
- `POST /quotes/generate` with `"use_ocerp": true` or `POST /quotes/generate-boq`
  — triggers BoQ generation instead of the lightweight local RAG path.

The microservice reads from the same PostgreSQL `cost_items` table and Qdrant
`cost_items` collection used by the API. It keeps any AGPL estimation code out
of the proprietary codebase by enforcing an HTTP-only boundary.

## Retrieval code

The relevant modules are:

- `services/api/app/rag/retrieval.py` — embedding + Qdrant search
- `services/api/app/rag/generation.py` — LLM prompt and JSON parsing
- `services/api/app/rag/validation.py` — mapping and confidence scoring
- `services/api/app/routers/quotes.py` — `POST /quotes/generate`
- `services/ocerp/app/services/boq_engine.py` — BoQ generation backend
