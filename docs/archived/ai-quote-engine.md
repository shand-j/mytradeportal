# AI Quote Engine

The RAG (Retrieval-Augmented Generation) Quote Engine turns a plain-language job
description into a draft quote grounded in real cost data.

## How it works

1. **Embed the query** — the job description is sent to an embedding model.
2. **Vector search** — Qdrant returns the most similar cost items, filtered by
   trade (`electrical`) and region (`UK`).
3. **LLM generation** — an OpenAI chat model receives the retrieved
   items, business pricing rules and the job description, then returns a JSON
   line-item list.
4. **Validation** — the response is mapped back to retrieved items, sanity
   checked and scored for confidence.
5. **Quote creation** — a draft `Quote` with line items is saved in PostgreSQL.

## Cost database

The cost database has two sources:

- **Domestic pipeline** — live Screwfix product data scraped via Apify,
  normalised and loaded by `python -m data_pipeline.loader`. Existing Apify
  datasets can also be imported with `python -m data_pipeline.import_apify_dataset
  <dataset-id>`.
- **DDC CWICR UK** — ~4,200 electrical scope-of-work rows from the
  OpenConstructionERP project, downloaded and ingested by
  `services/api/app/ingest_ddc_uk.py`.

Both sources are stored in PostgreSQL and embedded into Qdrant.

## Removing stale seed data

If the database still contains legacy `curated_seed` items from earlier
prototypes, delete them with:

```bash
cd services/data-pipeline
python -m data_pipeline.scripts.delete_curated_seed --execute
```

Run without `--execute` first to see the row counts by source.

## Configuration

Relevant environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI key — mandatory in all environments |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model passed to LiteLLM |
| `LLM_MODEL` | `gpt-4o-mini` | Chat model passed to LiteLLM |
| `QDRANT_URL` | `http://localhost:6333` | Vector database |
| `QDRANT_COLLECTION_NAME` | `cost_items` | Qdrant collection |
| `EMBEDDING_DIMENSIONS` | `1536` | Vector size (matches the default model) |

## Ingestion scripts

```bash
# Load Screwfix data via the Apify pipeline
cd services/data-pipeline
python -m data_pipeline.loader

# Or import an existing Apify dataset
cd services/data-pipeline
python -m data_pipeline.import_apify_dataset <dataset-id>

# Ingest the larger DDC CWICR UK electrical cost database
cd services/api
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
