# agentmem

Generic pluggable agent memory library. Evidence ledger, facet store, knowledge graph, progressive digests, active context, and vector search — deployable as a FastAPI service, importable as a Python library, and accessible from the shell via the `am` CLI.

Extracted from `paia-memory`. No paia coupling. Any agent can use it.

---

## What it does

agentmem gives agents durable, queryable memory across conversations. It handles the full storage lifecycle so your agent only has to do two things: **ingest** events as they happen and **retrieve** context when it needs to respond.

The memory loop:

```
Agent turn
    │
    ▼
POST /ingest/evidence          ← store what happened (raw event)
    │
    ▼ (async, background)
EmbedReindexJob                ← embed evidence into pgvector
    │
    ▼
DigestGenerationJob            ← daily/weekly rollups of older turns
    │
    ▼
At next turn: GET /retrieve/*  ← pull relevant context back into prompt
```

The five retrieval primitives map directly to the five lanes of context an agent needs:

| Lane | What it is | Endpoint |
|---|---|---|
| `identity_facets` | Stable identity, tone, relationship state | `GET /retrieve/facets` |
| `recent_turns` | Verbatim recent conversation evidence | `GET /retrieve/turns`, `GET /retrieve/evidence` |
| `rolling_summary` | Compressed digest of older turns | `GET /retrieve/summary`, `GET /retrieve/digests` |
| `semantic_recall` | pgvector cosine search over all memory | `GET /retrieve/semantic` |
| `graph_recall` | Subject-predicate-object triplet recall | `GET /retrieve/graph`, `POST /retrieve/echoes` |
| `world_state` | Live context atoms (schedule, obligations) | `GET /retrieve/context` |

Context assembly — combining these lanes into a prompt payload with lane weights and token budgets — is intentionally the caller's responsibility. agentmem provides the primitives; your agent or runtime decides how to blend them.

---

## Architecture

Five layers. Clean dependency direction — each layer only imports from layers above it:

```
┌──────────────────────────────────────────────┐
│  CLI  (`am` command, Typer, JSON output)     │  layer 5
├──────────────────────────────────────────────┤
│  Service  (FastAPI: /ingest /retrieve /admin)│  layer 4
├──────────────────────────────────────────────┤
│  Workers  (coordinator + 4 background jobs)  │  layer 3
├──────────────────────────────────────────────┤
│  Adapters  (Postgres/pgvector, Ollama, ...)  │  layer 2
├──────────────────────────────────────────────┤
│  Core  (domain logic + Protocol ABCs)        │  layer 1
└──────────────────────────────────────────────┘
```

The core layer has **zero concrete imports**. Every storage and embedding technology lives in adapters. Domain services depend only on Protocol ABCs — swap Postgres for SQLite or Ollama for OpenAI without touching any business logic.

---

## Quick start

```bash
# Install with Postgres + service extras
pip install agentmem[service,postgres]

# Set connection
export AGENTMEM__STORAGE__DSN="postgresql://user:pass@localhost:5432/agentmem"
export AGENTMEM__EMBEDDINGS__BASE_URL="http://localhost:11434"  # Ollama
export AGENTMEM__EMBEDDINGS__MODEL="nomic-embed-text"

# Run migrations and start the service
am admin migrate
uvicorn agentmem.service.app:create_app --factory --port 3510

# Ingest an event
am ingest evidence --tenant myagent \
  --event-type message \
  --content "User asked about project deadline"

# Retrieve context before responding
am retrieve semantic --tenant myagent --q "project deadline" --limit 5
am retrieve context --tenant myagent
am retrieve evidence --tenant myagent --limit 20
```

---

## Storage model

### Evidence (raw events)

Every conversation turn, tool call, observation, or external event is an `EvidenceRecord`. It is the atomic unit of memory.

```
EvidenceRecord
  tenant_id       str       — namespace (agent ID, user ID, session ID, ...)
  event_type      str       — "message" | "action" | "observation" | custom
  content         str       — full text content
  occurred_at     datetime  — when it happened (UTC)
  source_event_id str       — upstream message/event ID for deduplication
  dedupe_key      str       — idempotent insert key (same key = skip, not error)
  metadata        dict      — structured extras (conversation_id, platform, ...)
  channel_id      str|None  — optional channel/thread scope
```

Embeddings are stored separately in the vector store — never as a column on the evidence row. The `EmbedReindexJob` runs on a schedule and backfills any evidence without a vector entry.

### Facets (key-value memory)

Facets are structured facts about the agent or its relationships. They are intended to be stable and high-signal — not raw events.

```
FacetRecord
  tenant_id   str    — namespace
  key         str    — namespaced key, e.g. "persona.tone", "relationship.user.affect"
  value       str    — string value (JSON strings accepted)
  confidence  float  — 0.0–1.0
  layer       str    — "identity" | "runtime" | "derived"
```

Facets support prefix queries: `am facet list --tenant myagent --prefix persona.` returns all persona facets.

### Knowledge graph (triplets)

```
Triplet
  subject    str    — entity name
  predicate  str    — relationship verb
  object     str    — target entity or value
  confidence float
  source     str    — where this was derived from
```

Triplets are retrieved by subject, object, or predicate. They serve as the "poetic recall" layer — non-literal relationship continuity for agents that maintain relationship models.

### Digests (rolling summaries)

The `DigestGenerationJob` produces deterministic summaries (concatenated evidence) on a daily/weekly/monthly schedule. Each digest covers a time window and is upserted — re-running the same period overwrites the previous result.

```
Digest
  tenant_id    str
  digest_type  str       — "daily" | "weekly" | "monthly"
  period_start datetime
  period_end   datetime
  content      str       — concatenated "[event_type] content" lines
```

**v1 note:** Digest content is deterministic (concatenation), not LLM-generated. LLM-generated summaries are v2. Digests are triggered on a cron schedule (daily at midnight UTC, weekly on Monday, monthly on the 1st) and also via turn-count triggers (`TurnCountTrigger`). Digests are embedded to pgvector alongside evidence and facets.

### Active context (living atoms)

Named context sections with a TTL. Updated continuously by the `ActiveContextJob` as events arrive. Agents pull these before every response for current world-state (schedule, active task, current obligations).

```
ContextSection
  tenant_id  str
  section    str       — "current_task" | "schedule" | "recent_alerts" | custom
  content    str       — latest content for this section
  updated_at datetime
```

Query with `max_age_seconds` to filter stale sections:

```bash
am context get --tenant myagent --max-age-seconds 3600
```

---

## Background jobs

Four jobs run automatically under `WorkerCoordinator`:

| Job | Trigger | What it does |
|---|---|---|
| `embed_reindex` | `cron: 0 * * * *` (hourly) | Embeds any evidence/facet rows missing a vector entry |
| `digest_generation` | `cron: 0 0 * * *` (daily) | Generates daily (and weekly/monthly when applicable) digests |
| `retention` | `cron: 0 2 * * *` (2am daily) | Prunes evidence older than `evidence_days` (default 180) |
| `active_context` | `continuous: pg_listen` | Updates context sections as events arrive via LISTEN/NOTIFY |

The coordinator handles crash recovery (exponential backoff: 1s → 2s → 4s → 8s → 16s), heartbeat monitoring, and in-process pub/sub between jobs.

---

## Configuration

All config via environment variables with the `AGENTMEM__` prefix (double-underscore for nesting):

```bash
# Storage
AGENTMEM__STORAGE__DSN=postgresql://user:pass@localhost:5432/agentmem
AGENTMEM__STORAGE__POOL_MIN=2
AGENTMEM__STORAGE__POOL_MAX=10

# Embeddings
AGENTMEM__EMBEDDINGS__BASE_URL=http://localhost:11434
AGENTMEM__EMBEDDINGS__MODEL=nomic-embed-text
AGENTMEM__EMBEDDINGS__DIMENSIONS=4096

# Multi-tenancy
AGENTMEM__TENANCY__DEFAULT_TENANT=default
AGENTMEM__TENANCY__ALLOW_CROSS_TENANT=false

# Workers
AGENTMEM__WORKERS__EMBED_REINDEX__BATCH_SIZE=100
AGENTMEM__WORKERS__DIGEST__TENANTS=["agent1","agent2"]
AGENTMEM__WORKERS__RETENTION__EVIDENCE_DAYS=180

# Service
AGENTMEM__ADMIN__ENABLED=true
AGENTMEM__ADMIN__TOKEN=your-secret-token
```

Or via `agentmem.toml` in the working directory (same keys, TOML format).

---

## API reference

### Ingest

```
POST /ingest/evidence     — store a new evidence record
POST /ingest/facet        — set a facet value
POST /ingest/triplet      — add a knowledge graph edge
POST /context/set         — upsert an active context section
```

### Retrieve

```
GET  /retrieve/evidence    — recent events (filter by type, since, channel)
GET  /retrieve/turns       — conversation turns (filter by conversation_id, channel_id)
GET  /retrieve/summary     — rolling digest of older turns grouped by date
GET  /retrieve/semantic    — pgvector cosine search over embedded memory
GET  /retrieve/facets      — facet list (filter by prefix, layer)
GET  /retrieve/graph       — triplet query (by subject, predicate, or object)
POST /retrieve/echoes      — poetic recall blocks from proper nouns + graph triplets
GET  /retrieve/digests     — list stored digests (filter by type)
GET  /retrieve/context     — active context sections (filter by max_age_seconds)
```

### Admin

```
POST /admin/reindex             — trigger embedding backfill
POST /admin/retention           — run data pruning
GET  /admin/stats               — row counts per store per tenant
POST /admin/digest/generate     — on-demand digest generation
POST /workers/run/{job_name}    — trigger any registered job on-demand
GET  /workers/status            — job health and last-run info
```

---

## CLI (`am`)

All commands output newline-delimited JSON. Set `AGENTMEM_URL` and `AGENTMEM_TENANT` to avoid passing flags on every call.

```bash
export AGENTMEM_URL=http://localhost:3510
export AGENTMEM_TENANT=myagent

# Ingest
am ingest evidence --event-type message --content "..."
am ingest facet persona.tone "warm and direct" --confidence 0.9
am ingest triplet agent0 "prefers" "direct answers" --confidence 1.0

# Retrieve
am retrieve evidence --limit 20
am retrieve semantic --q "what did we discuss last Tuesday"
am retrieve facets --prefix persona.

# Facets
am facet get persona.tone
am facet list --prefix relationship.
am facet set persona.tone "concise" --layer identity

# Graph
am graph query --subject agent0
am graph add agent0 "works on" agentmem

# Context
am context get --max-age-seconds 3600
am context set --section current_task --content "debugging embed pipeline"
am context delete --section current_task

# Digest
am digest list --type daily --limit 7

# Admin
am admin stats
am admin reindex --dry-run
am admin workers-status
```

---

## Python library usage

```python
from agentmem.adapters.storage.postgres import PostgresStorageAdapter
from agentmem.adapters.embeddings.ollama import OllamaEmbeddingAdapter
from agentmem.core.evidence import EvidenceLedger
from agentmem.core.embeddings import EmbeddingService
from agentmem.core.models import EvidenceRecord, EvidenceFilters, VectorFilters
from datetime import datetime, timezone

# Setup
storage = PostgresStorageAdapter(dsn="postgresql://...")
embed_adapter = OllamaEmbeddingAdapter(base_url="http://localhost:11434", model="nomic-embed-text")
await storage.initialize()
await storage.migrate()

ledger = EvidenceLedger(evidence_store=storage, vector_store=storage, embed_adapter=embed_adapter)
embedding_service = EmbeddingService(adapter=embed_adapter, store=storage)

# Ingest a turn
record = EvidenceRecord(
    tenant_id="myagent",
    event_type="message",
    content="User asked about the project deadline.",
    occurred_at=datetime.now(timezone.utc),
    source_event_id="msg-001",
    dedupe_key="msg-001",
    metadata={"conversation_id": "conv-42", "platform": "slack"},
)
await ledger.ingest(record)

# Retrieve context for the next turn
filters = VectorFilters(tenant_id="myagent", limit=5)
results = await embedding_service.search("project deadline", filters)
for r in results:
    print(r.source_table, r.source_id, r.score)
```

---

## Extending agentmem

### Custom storage adapter

Implement the Protocol ABCs in `agentmem.core.protocols`. A single class can implement all six store protocols (as `PostgresStorageAdapter` does) or you can implement them separately.

```python
from agentmem.core.protocols import EvidenceStore, VectorStore
from agentmem.core.models import EvidenceRecord, InsertResult, EvidenceFilters

class MyStorageAdapter:
    async def initialize(self) -> None: ...
    async def close(self) -> None: ...
    async def migrate(self) -> None: ...
    async def insert(self, record: EvidenceRecord) -> InsertResult: ...
    async def query(self, filters: EvidenceFilters) -> list[EvidenceRecord]: ...
    # ... implement remaining protocols
```

### Custom embedding adapter

```python
from agentmem.core.protocols import EmbeddingAdapter

class MyEmbeddingAdapter:
    model_id = "my-model-v1"
    dimensions = 1536

    async def embed(self, text: str) -> list[float] | None:
        # return None on service unavailable — callers handle gracefully
        ...

    async def close(self) -> None: ...
```

### Custom worker job

```python
from agentmem.workers.coordinator import ScheduledJob, JobContext, JobResult
from agentmem.workers.triggers import CronTrigger

class MyJob(ScheduledJob):
    name = "my_job"
    trigger = CronTrigger(schedule="0 3 * * *")  # 3am daily

    async def run(self, context: JobContext) -> JobResult:
        # context.evidence_ledger, context.embedding_service, etc.
        await context.heartbeat()
        return JobResult(success=True, items_processed=0)
```

Register it on startup:

```python
coordinator.register(MyJob())
```

---

## Agent integration guide

> **This section is written for agents consuming agentmem as infrastructure.**  
> If you are an agent being initialized with agentmem as your memory backend, read this section.

### What agentmem is

agentmem is your persistent memory. Everything you experience — messages, observations, tool results, inferred facts — should be ingested here. At the start of each response, you retrieve relevant context from here and include it in your reasoning.

You do not need to remember anything yourself. agentmem remembers for you.

### Memory loop (every turn)

**Step 1 — Before responding:** Pull context.

```bash
# Get living context atoms (schedule, current task, recent alerts)
am context get --max-age-seconds 3600

# Get the last 20 conversation turns
am retrieve evidence --limit 20 --event-type message

# Semantic search for anything relevant to this turn's query
am retrieve semantic --q "<current user message>" --limit 5

# Get identity and relationship facets
am retrieve facets --prefix persona.
am retrieve facets --prefix relationship.

# Get recent digest (compressed older memory)
am digest list --type daily --limit 3
```

Combine these lanes with your own weighting. The semantic search and facets are the highest signal for most turns. Digests become important when the user references something from days ago.

**Step 2 — After responding:** Ingest what happened.

```bash
# Store the turn as evidence
am ingest evidence \
  --event-type message \
  --content "<user message> | <your response>" \
  --metadata '{"conversation_id":"<id>","user_message":"...","agent_response":"..."}'

# Update any facets that changed
am ingest facet relationship.user.affect "positive" --confidence 0.8

# Add any new knowledge graph facts
am ingest triplet "<subject>" "<learned relationship>" "<object>"
```

### Deduplication

Always set `--dedupe-key` to the upstream message ID. agentmem will skip duplicate inserts silently — safe to call ingest on retry or at-least-once delivery without creating duplicate memory.

### Tenant isolation

All memory is scoped to `tenant_id`. Use a stable identifier for each agent instance or user relationship. Cross-tenant retrieval is disabled by default.

### What agentmem does NOT do

- It does not assemble your prompt. You decide how to blend the retrieval lanes.
- It does not generate LLM summaries (v1). Digests are deterministic concatenations.
- It does not inject context automatically. You call the retrieval endpoints.
- It does not manage your conversation loop or model selection.

### What your runtime layer should add on top

If you are building on agentmem for a companion/assistant agent, you will want to add:

- **Context assembly**: blend the five retrieval lanes into a single prompt section with token budgeting
- **Poetic/relationship recall formatting**: the `/retrieve/echoes` endpoint returns `word/word/word` blocks; wrap these into natural-language phrases for your agent's persona layer

---

## Tenancy model

agentmem is single-tenant by default. Multi-tenancy is achieved by namespacing all records under `tenant_id`. There is no auth between tenants — isolation is by convention. If you are running a multi-tenant deployment, put agentmem behind a gateway that enforces tenant_id scoping on every request.

Cross-tenant facet blending (`list_multi`) is available for shared-knowledge scenarios (e.g. a shared organizational graph read by multiple agent tenants).

---

## Schema (Postgres)

```sql
-- Events / conversation turns
CREATE TABLE evidence (
    id              bigserial PRIMARY KEY,
    tenant_id       text NOT NULL,
    event_type      text NOT NULL,
    content         text NOT NULL,
    occurred_at     timestamptz NOT NULL,
    source_event_id text,
    dedupe_key      text UNIQUE,
    metadata        jsonb DEFAULT '{}',
    channel_id      text
);

-- Structured facts
CREATE TABLE facets (
    id          bigserial PRIMARY KEY,
    tenant_id   text NOT NULL,
    key         text NOT NULL,
    value       text NOT NULL,
    confidence  float NOT NULL DEFAULT 1.0,
    layer       text NOT NULL DEFAULT 'runtime',
    UNIQUE (tenant_id, key)
);

-- Knowledge graph
CREATE TABLE knowledge_graph (
    id          bigserial PRIMARY KEY,
    tenant_id   text NOT NULL,
    subject     text NOT NULL,
    predicate   text NOT NULL,
    object      text NOT NULL,
    confidence  float NOT NULL DEFAULT 1.0,
    source      text
);

-- Time-windowed summaries
CREATE TABLE digests (
    id           bigserial PRIMARY KEY,
    tenant_id    text NOT NULL,
    digest_type  text NOT NULL,
    period_start timestamptz NOT NULL,
    period_end   timestamptz NOT NULL,
    content      text NOT NULL,
    UNIQUE (tenant_id, digest_type, period_start)
);

-- Living context atoms
CREATE TABLE active_context (
    id         bigserial PRIMARY KEY,
    tenant_id  text NOT NULL,
    section    text NOT NULL,
    content    text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, section)
);

-- Vector embeddings (HNSW index via pgvector)
CREATE TABLE embeddings (
    id           bigserial PRIMARY KEY,
    tenant_id    text NOT NULL,
    source_table text NOT NULL,
    source_id    bigint NOT NULL,
    model_id     text NOT NULL,
    embedding    vector(4096),
    collection   text NOT NULL DEFAULT 'default',
    UNIQUE (source_table, source_id, model_id)
);
CREATE INDEX ON embeddings USING hnsw (embedding vector_cosine_ops);
```

---

## v1 known limitations

- **LLM-generated summaries**: Digest content is deterministic (concatenation of evidence lines). LLM rollup summarization is v2.
- **SQLite adapter**: Postgres is the only shipped storage adapter. SQLite is planned for v2 (single-process / embedded deployments).
- **Echoes endpoint**: Poetic recall (`POST /retrieve/echoes`) requires a graph store with existing triplets. Cold-start agents with no graph data will get empty echo blocks.

---

## Development

```bash
git clone https://github.com/dbmcco/agentmem
cd agentmem
uv sync --all-extras
.venv/bin/python -m pytest tests/ --ignore=tests/integration
```

Integration tests require a live Postgres instance with pgvector:

```bash
AGENTMEM__STORAGE__DSN="postgresql://..." \
  .venv/bin/python -m pytest tests/integration/
```

---

## License

MIT
