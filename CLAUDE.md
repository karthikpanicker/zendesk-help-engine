# CLAUDE.md — Zendesk Workflow Suggestion Engine

## Project purpose

Real-time AI assistant for Zendesk support agents. 60% of support tickets are workflow-related clarification questions (PTO, expense reports, IT access, etc.). This system:
1. **Ingests** historical workflow-tagged Zendesk data (tickets, chats, call transcripts, Help Center articles) into a vector knowledge base
2. **Surfaces** contextual suggestions to agents via a Zendesk sidebar app as customers type during live chats

## Architecture

```
Zendesk APIs (Tickets, Chat/Sunshine, Talk, Guide)
        │  filtered by workflow tags in config.yaml
        ▼
  Ingestion Pipeline  ──►  ChromaDB (./data/chroma/)
  (scripts/run_ingestion.py)       │
                                   ▼
Live chat → ZAF sidebar (zaf-app/) → POST /suggest → RAG pipeline → Claude → suggestion card
```

## Tech stack

- **Backend**: Python 3.12 + FastAPI + uvicorn
- **Embeddings**: `BAAI/bge-base-en-v1.5` via `sentence-transformers` (local, zero cost). Switchable to Voyage AI via `config.yaml`
- **Vector store**: ChromaDB (file-persisted at `./data/chroma/`)
- **LLM**: `claude-sonnet-4-6` via Anthropic SDK
- **Frontend**: Zendesk Apps Framework (ZAF) — plain HTML/JS sidebar app

## Key files

| File | Role |
|---|---|
| `config/config.yaml` | **Single source of truth** for all operator settings — Zendesk credentials, workflow tags, model choice, RAG thresholds |
| `backend/config.py` | Pydantic Settings; reads config.yaml + expands `${ENV_VAR}` placeholders |
| `backend/main.py` | FastAPI entrypoint; wires routers and CORS |
| `backend/ingestion/runner.py` | Orchestrates all four Zendesk data sources concurrently → chunks → embed → upsert |
| `backend/ingestion/embedder.py` | Embedding abstraction; `embed_documents()` for storage, `embed_query()` for retrieval |
| `backend/rag/suggester.py` | Core RAG loop: retrieve → build prompt → call Claude → return suggestion |
| `backend/rag/prompt_builder.py` | Claude system + user prompt; the system prompt is the guardrail (no fabrication) |
| `backend/routers/suggest.py` | `POST /suggest`; tag classification fast-path before any LLM call |
| `zaf-app/src/app.js` | ZAF event wiring: `app.activated`, `ticket.conversation.message.created`, `ticket.tags.changed` |
| `zaf-app/src/suggest.js` | Backend HTTP call via `client.request()` + DOM rendering |
| `scripts/mock_zendesk_server.py` | FastAPI mock of Zendesk APIs serving fixture JSON — for local dev without a real account |

## Environment setup

```bash
cp .env.example .env
# Fill in: ZENDESK_API_TOKEN, ANTHROPIC_API_KEY
# Optional: VOYAGE_API_KEY (only if embeddings.provider = "voyage")

pip install -r requirements.txt
```

## Common commands

```bash
# Run backend (local dev)
uvicorn backend.main:app --reload --port 8000

# Run ingestion against real Zendesk
python scripts/run_ingestion.py

# Run ingestion against mock Zendesk (no real account needed)
uvicorn scripts.mock_zendesk_server:app --port 9000 &
ZENDESK_BASE_URL=http://localhost:9000 python scripts/run_ingestion.py

# Run tests (all mocked — no API keys required)
pytest

# ZAF sidebar local dev (requires @zendesk/zcli)
npm install -g @zendesk/zcli
zcli apps:server zaf-app/

# Docker
docker compose up                          # backend only
docker compose --profile dev up            # backend + mock Zendesk server
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check; returns doc count + model info |
| `POST` | `/suggest` | Real-time suggestion; called by ZAF sidebar |
| `POST` | `/ingest` | Trigger background re-ingestion of all sources |
| `GET` | `/ingest/status/{task_id}` | Poll ingestion progress |

### `/suggest` contract

```json
// Request
{
  "ticket_id": "12345",
  "current_message": "How do I submit a half-day PTO?",
  "ticket_tags": ["workflow-question", "hr"]
}

// Response — workflow ticket
{
  "is_workflow_question": true,
  "suggestion": "To submit a half-day PTO...",
  "sources": [{ "source_type": "ticket", "title": "...", "url": "...", "score": 0.87 }],
  "retrieved_count": 3
}

// Response — non-workflow ticket (fast path, no LLM call)
{
  "is_workflow_question": false,
  "suggestion": null,
  "sources": [],
  "retrieved_count": 0
}
```

## Configuration reference (`config/config.yaml`)

```yaml
workflow:
  tags:                    # tickets with ANY of these tags activate suggestions
    - "workflow-question"

embeddings:
  provider: "local"        # "local" (BGE, zero cost) | "voyage" (better accuracy)
  local_model: "BAAI/bge-base-en-v1.5"

rag:
  top_k: 5                 # chunks to retrieve
  min_score: 0.35          # cosine similarity threshold; lower = more results, less precise
  suggestion_max_tokens: 300

ingestion:
  chunk_size: 512          # characters per chunk
  chunk_overlap: 64
```

Changing workflow tags, thresholds, or embedding provider requires a server restart. Changing tags also means re-running ingestion.

## Classification logic

Tag-based, not LLM-based. Two enforcement points:

1. **Ingestion time**: Only tickets/chats/articles whose Zendesk tags overlap with `workflow.tags` are ingested into ChromaDB. This defines what the knowledge base contains.
2. **Request time** (`/suggest`): The endpoint does a set intersection of `ticket_tags` (from ZAF) vs `workflow.tags`. If no overlap → returns immediately, no embedding or LLM call. This is the fast path.

To expand coverage: add more tags to `config.yaml`. No code changes needed.

## Ingestion sources

| Source | API used | How workflow filter works |
|---|---|---|
| Tickets | `GET /api/v2/search.json?query=type:ticket tags:...` | Tags in search query |
| Chat | Sunshine Conversations → fallback to legacy Zopim API | `filter[tags]` param / client-side |
| Talk | Transcripts live as ticket comments (Talk auto-creates them) | Captured by tickets ingestor |
| Guide | `GET /api/v2/help_center/articles` | `label_names` overlap or title keyword match |

Document IDs are `{source_type}_{id}_chunk{n}` — upserts are idempotent so re-running ingestion is safe.

## Testing

All tests mock external dependencies (Anthropic, embedder, ChromaDB). No API keys needed to run tests.

```bash
pytest                     # run all tests
pytest backend/tests/test_api.py        # API layer only
pytest backend/tests/test_rag.py        # RAG pipeline only
pytest backend/tests/test_ingestion.py  # chunker, embedder, guide filter
```

Key fixtures in `backend/tests/conftest.py`:
- `mock_collection` — in-memory ChromaDB pre-seeded with 4 workflow chunks
- `mock_settings` — Settings with `min_score=0.0` (all test vectors pass) and fake API keys
- `client` — FastAPI TestClient with all external deps patched

## ZAF app conventions

- **All HTTP to backend must use `client.request()`** — direct `fetch()` is blocked by ZAF sandbox
- `backendUrl` is a ZAF install parameter set at deploy time; never hardcode it
- The app has 4 states: `inactive` / `loading` / `suggestion` / `error` — toggled via `showState()` in `suggest.js`
- ZAF app activates the suggestion panel only when `ticket.tags` contain a workflow keyword (`isWorkflowTicket()` in `app.js`)
- Resize the iframe via `client.invoke('resize', ...)` after state transitions

## Embedding providers

| Provider | Config | Cost | Dims | Notes |
|---|---|---|---|---|
| `local` (default) | `embeddings.provider: local` | Free | 768 | First run downloads ~440MB model to `~/.cache/huggingface` |
| `voyage` | `embeddings.provider: voyage` + `VOYAGE_API_KEY` | $0.06/1M tokens | 1024 | Better accuracy; 200M tokens free/month |

Both use the same `embed_documents()` / `embed_query()` interface in `backend/ingestion/embedder.py`.

## Adding a new Zendesk data source

1. Create `backend/ingestion/{source}.py` following the pattern of `tickets.py` or `guide.py`
2. Return a list of objects with: `doc_id`, `text`, `title`, `tags`, `url`, `source_type`
3. Add it to `run_ingestion()` in `backend/ingestion/runner.py` alongside the existing `asyncio.gather()` call
4. Add fixture JSON in `tests/fixtures/` and a route in `scripts/mock_zendesk_server.py`

## What not to do

- **Do not add multi-agent / agent loops to the `/suggest` path** — latency must stay under 2s. Multi-hop Claude calls would push this to 5-15s, unusable in live chat.
- **Do not call external APIs from ZAF JS with `fetch()`** — always use `client.request()`.
- **Do not hardcode API keys or URLs** anywhere in the codebase — all via `.env` + `config.yaml`.
- **Do not store secrets in `config.yaml`** — use `${ENV_VAR}` placeholders only.
- **Do not skip re-ingestion after changing `workflow.tags`** — the knowledge base only contains data that matched tags at ingestion time.
- **Do not use `get_settings()` outside of FastAPI `Depends()`** in router files — it is `lru_cache`'d and safe, but DI makes testing easier.

## Future extension points

- **Agentic ingestion enricher**: Replace raw chunking with a Claude agent that reads each ticket and generates a structured Q&A before embedding. Runs offline so latency doesn't matter. Would significantly improve retrieval quality.
- **Domain routing**: A lightweight classifier to route queries to domain-specific ChromaDB collections (HR, IT, Finance) if cross-domain retrieval noise becomes a problem.
- **Feedback loop**: Track which suggestions agents act on (copy/use) and re-weight the knowledge base accordingly.
