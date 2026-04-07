# agentmem

Generic pluggable agent memory library. Evidence ledger, facet store, knowledge graph, progressive digests, active context, and vector search — deployable as a FastAPI service, importable as a Python library, and accessible from the shell via the CLI.

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

agentmem provides the retrieval primitives. Context assembly — blending these lanes into a prompt with weights and token budgets — is intentionally the caller's responsibility.

---

## How this differs from other approaches

Most agent memory systems fall into one of two patterns: **conversation buffers** (keep recent turns, truncate when full) or **RAG over history** (embed everything, retrieve by similarity). Both work for simple cases. Neither handles the full range of what an agent actually needs to remember.

### The core problem with monolithic memory

When memory is a single bucket — whether a rolling buffer or a vector index — every retrieval decision is the same decision: *how similar is this to the current query?* That works for topic continuity. It fails for everything else.

An agent that has had 10,000 conversations with you should still know your name without it having to "win" a cosine similarity contest against recent messages. It should know your preferred communication style unconditionally. It should know what happened in the conversation five minutes ago without vector search latency. And it should know what is happening *right now* without any historical retrieval at all.

These are four fundamentally different memory problems. Solving them with a single mechanism means compromising all four.

### What agentmem does instead

**Identity is unconditional.** Facets — stable facts about the agent's persona and its relationship with the user — are retrieved as structured key-value data and injected first, without a similarity threshold. They cannot be crowded out by recent events. This is the most important architectural decision in the system.

**Memory has layers, not just recency.** The retrieval architecture separates six distinct signals:

- What the agent *is* (identity facets — unconditional)
- What is happening *right now* (world state — live, event-driven)
- What was *just said* (recent turns — verbatim, recency-ordered)
- What was said *some time ago, compressed* (rolling digests — time-structured)
- What is *relevant to this specific query* (semantic recall — similarity-gated)
- What is *factually known* about entities in play (graph recall — relationship-structured)

Each lane answers a different question. Collapsing them into one loses the distinction.

**Context assembly is the caller's job.** agentmem does not inject context into prompts automatically. It does not decide how much weight to give identity vs. recent turns vs. semantic recall. That decision belongs to the agent or runtime — it depends on the query type, the persona, the token budget, and factors the library cannot know. This is a constraint that forces good architecture upstream.

**Memory maintenance is deterministic.** Background jobs handle embedding backfill, digest generation, and retention pruning on schedule. No LLM is required to manage memory. Digests are deterministic concatenations — not AI summaries — which makes them cheap, predictable, and auditable. (LLM-generated rollup summarization is a planned v2 feature for callers who want it.)

**Confidence is first-class.** Facets carry a confidence score (0.0–1.0). A fact the agent learned from explicit user input (confidence 1.0) is different from a fact inferred from behavioral patterns (confidence 0.7). This lets downstream logic weight or filter facts by certainty rather than treating all memory as equally reliable.

### Compared to specific systems

| System | What it does well | What agentmem adds |
|---|---|---|
| **LangChain memory** | Simple conversation buffer / summary chain | Structured facet identity, graph layer, multi-lane retrieval, background workers |
| **MemGPT** | LLM manages its own memory; paging in/out | Deterministic (no LLM for memory ops), explicit lane separation, pluggable adapters |
| **Zep** | Turn storage + entity extraction + vector search | Identity facets, confidence scoring, turn-count triggers, full protocol-driven extensibility |
| **mem0** | AI-extracted memory with dedup | Deterministic maintenance, identity layer, no inference required to store or retrieve |
| **Plain RAG** | Similarity search over arbitrary text | All of the above |

agentmem is not trying to replace systems that use LLMs to manage memory. It is an alternative philosophy: **give the agent precise, well-structured retrieval primitives and let it decide how to reason about them**, rather than using another model to summarize, extract, and manage memory on its behalf.

---

## Context injection

### Philosophy

The central idea is that context is not monolithic. A well-assembled context window is five distinct signals stacked in priority order, each serving a different purpose:

- **Identity facets** anchor *who the agent is* and *how it relates to this user*. These are the most stable and least token-intensive. They go first and get clipped last.
- **World state** captures *what is happening right now*. Schedule, active task, current obligations. This changes on every turn and must be current.
- **Recent turns** provide verbatim memory of *what was just said*. Recency matters most here — fetch the last N turns and include them verbatim.
- **Rolling summary** bridges *what was said days ago*. Digests are compressed chronologically — include the most recent digest first, then older ones as budget allows.
- **Semantic recall** surfaces *what is relevant to this specific query* regardless of when it happened. Run a vector search against the current user message. This is the highest-signal lane for topic continuity.
- **Graph recall / echoes** adds *relational texture* — known facts about entities mentioned in this turn. Triplets like `agent0 / prefers / direct answers` reinforce persona and relationship context.

The rule: **recency beats depth, but semantic relevance can override recency.** A message from three weeks ago that scores 0.92 cosine similarity to the current query is more useful than a message from yesterday that scores 0.3.

### Token budget

Token budgets are not one-size-fits-all, but a reasonable starting allocation for a 4K context window looks like this:

| Lane | Suggested budget | Why |
|---|---|---|
| Identity facets | 300–500 tokens | Stable; clippping it hurts persona consistency |
| World state | 100–200 tokens | Short atoms; usually just a few key-value pairs |
| Recent turns | 800–1500 tokens | Verbatim is expensive but necessary for coherence |
| Rolling summary | 400–800 tokens | Compressed digest — recent daily first, then weekly |
| Semantic recall | 400–800 tokens | Top 3–5 results; clip by score threshold (e.g. ≥ 0.70) |
| Graph recall | 100–200 tokens | Triplets are compact; include up to ~10 |

For 8K–16K context windows, expand recent turns and rolling summary first. Semantic recall rarely needs more than 5–8 results regardless of budget.

### Injection point

Inject assembled context into the **system prompt**, not the user turn. The system prompt persists across the conversation turn and is processed before the user message, which is the right evaluation order.

Recommended structure:

```
[SYSTEM PROMPT]

<identity>
{identity_facets}
</identity>

<world_state>
{world_state}
</world_state>

<memory>
## What we talked about recently
{recent_turns}

## Older context (compressed)
{rolling_summary}

## Relevant past context
{semantic_recall}

## Known facts
{graph_recall}
</memory>

[your agent instructions follow here]
```

The XML-style tags are optional but help the model treat memory as a distinct signal from instructions.

### Python example

```python
import httpx
from dataclasses import dataclass

AGENTMEM_URL = "http://localhost:3510"
TENANT = "myagent"

@dataclass
class ContextWindow:
    identity: str
    world_state: str
    recent_turns: str
    rolling_summary: str
    semantic_recall: str
    graph_recall: str

    def render(self) -> str:
        parts = []
        if self.identity:
            parts.append(f"<identity>\n{self.identity}\n</identity>")
        if self.world_state:
            parts.append(f"<world_state>\n{self.world_state}\n</world_state>")
        memory_sections = []
        if self.recent_turns:
            memory_sections.append(f"## Recent turns\n{self.recent_turns}")
        if self.rolling_summary:
            memory_sections.append(f"## Summary of older context\n{self.rolling_summary}")
        if self.semantic_recall:
            memory_sections.append(f"## Relevant past context\n{self.semantic_recall}")
        if self.graph_recall:
            memory_sections.append(f"## Known facts\n{self.graph_recall}")
        if memory_sections:
            parts.append("<memory>\n" + "\n\n".join(memory_sections) + "\n</memory>")
        return "\n\n".join(parts)


async def build_context(user_message: str, conversation_id: str) -> ContextWindow:
    async with httpx.AsyncClient(base_url=AGENTMEM_URL) as client:
        # Run all retrieval lanes in parallel
        import asyncio
        facets_r, world_r, turns_r, summary_r, semantic_r, graph_r = await asyncio.gather(
            client.get("/retrieve/facets", params={"tenant_id": TENANT, "prefix": "persona.", "limit": 20}),
            client.get("/retrieve/context", params={"tenant_id": TENANT, "max_age_seconds": 3600}),
            client.get("/retrieve/turns", params={"tenant_id": TENANT, "conversation_id": conversation_id, "limit": 20}),
            client.get("/retrieve/summary", params={"tenant_id": TENANT, "verbatim_count": 20, "limit": 5}),
            client.get("/retrieve/semantic", params={"tenant_id": TENANT, "q": user_message, "limit": 5, "min_score": 0.70}),
            client.get("/retrieve/graph", params={"tenant_id": TENANT, "limit": 10}),
        )

        # Format identity facets as key: value lines
        identity_lines = [f"{f['key']}: {f['value']}" for f in facets_r.json()]

        # Format world state atoms
        world_lines = [f"{s['section']}: {s['content']}" for s in world_r.json()]

        # Format turns as User/Agent pairs
        turn_lines = []
        for t in turns_r.json():
            if t.get("user_message"):
                turn_lines.append(f"User: {t['user_message']}")
            if t.get("agent_response"):
                turn_lines.append(f"Agent: {t['agent_response']}")

        # Format digests from summary endpoint
        summary_lines = [f"[{s['period_label']}] {s['content']}" for s in summary_r.json()]

        # Format semantic results — include score for transparency
        semantic_lines = [
            f"[score={r['score']:.2f}] {r['content']}" for r in semantic_r.json()
        ]

        # Format graph triplets
        graph_lines = [
            f"{t['subject']} / {t['predicate']} / {t['object']}" for t in graph_r.json()
        ]

        return ContextWindow(
            identity="\n".join(identity_lines),
            world_state="\n".join(world_lines),
            recent_turns="\n".join(turn_lines),
            rolling_summary="\n".join(summary_lines),
            semantic_recall="\n".join(semantic_lines),
            graph_recall="\n".join(graph_lines),
        )


# Usage
ctx = await build_context(user_message="What's the status on the project?", conversation_id="conv-42")
system_prompt = base_instructions + "\n\n" + ctx.render()
```

All six retrieval calls run concurrently via `asyncio.gather`. On a warm Postgres instance this round-trip is typically under 50ms.

### Lane weights in practice

Not all turns need all lanes. Tune based on query type:

| Query type | Lanes to emphasize |
|---|---|
| Continuing a thread | recent_turns (high), rolling_summary (medium) |
| "Do you remember when..." | rolling_summary (high), semantic_recall (high) |
| Task-focused ("write the email") | world_state (high), identity_facets (medium) |
| Relational question ("how do I usually...") | graph_recall (high), identity_facets (high) |
| First turn of a new conversation | identity_facets (high), world_state (high), semantic_recall (medium) |

The simplest weight system is just adjusting `limit` per lane — more results = more tokens = more signal. Start with the defaults above and tune based on observed coherence.

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

### 1. Start Postgres with pgvector

```bash
docker compose up -d
```

This starts `pgvector/pgvector:pg16` on port 5432 with database `agentmem`, user `agentmem`, password `agentmem`. If you already have a Postgres instance with pgvector installed, skip this step and set `AGENTMEM__STORAGE__DSN` to your DSN.

### 2. Install

```bash
pip install agentmem[service,cli,ollama]
# or with uv:
uv add agentmem[service,cli,ollama]
```

Extras:
- `service` — FastAPI HTTP service and uvicorn
- `cli` — the `am` shell command
- `ollama` — Ollama embedding adapter (local embeddings)
- `openai` — OpenAI embedding adapter
- `all` — everything

### 3. Configure

Create `agentmem.toml` in your working directory (or export environment variables):

```toml
[storage]
dsn = "postgresql://agentmem:agentmem@localhost:5432/agentmem"

[embeddings]
backend = "ollama"
url = "http://localhost:11434"
model = "nomic-embed-text"
dimensions = 768

[tenancy]
mode = "single"
default_tenant = "myagent"
```

Environment variable overrides use double-underscore separators:

```bash
export AGENTMEM__STORAGE__DSN="postgresql://agentmem:agentmem@localhost:5432/agentmem"
export AGENTMEM__EMBEDDINGS__URL="http://localhost:11434"
export AGENTMEM__EMBEDDINGS__MODEL="nomic-embed-text"
export AGENTMEM__TENANCY__DEFAULT_TENANT="myagent"
```

### 4. Migrate and start

```bash
am admin migrate
uvicorn agentmem.service.app:create_app --factory --port 3510
```

### 5. Bootstrap your agent's identity

Before your agent handles any turns, seed its identity facets. These anchor the context window on every response — without them the agent has no stable persona or relationship state to draw from.

```bash
export AGENTMEM_URL=http://localhost:3510
export AGENTMEM_TENANT=myagent

# Run the worked example (fictional agent + user, all layers, fully commented)
bash examples/bootstrap_facets.sh

# Prime the active context
am context set --section current_task --content "ready"
am context set --section schedule --content "no upcoming events"
```

See [Facets](#facets) for the full naming conventions, layer guide, and the minimum viable set.

### 6. Verify

```bash
# Check everything is wired
am admin stats --tenant myagent

# Test retrieval
am retrieve facets --tenant myagent --prefix persona.
am retrieve context --tenant myagent
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

Facets are structured facts about the agent or its relationships. They are stable and high-signal — not raw events. Where evidence captures *what happened*, facets capture *what is true*.

```
FacetRecord
  tenant_id   str    — namespace
  key         str    — dot-namespaced key, e.g. "persona.tone"
  value       str    — string value (JSON strings accepted for structured data)
  confidence  float  — 0.0–1.0
  layer       str    — "identity" | "runtime" | "derived"
```

#### Layers

| Layer | What it holds | Who writes it | Changes how often |
|---|---|---|---|
| `identity` | Stable persona, relationship state, user preferences | Bootstrapped by you; updated deliberately | Rarely (days to months) |
| `runtime` | Current mode, active project, session state | Agent writes during operation | Per-session or per-task |
| `derived` | Inferred facts from evidence patterns | DigestGenerationJob or your inference layer | As evidence accumulates |

#### Naming conventions

Keys use dot-namespaced hierarchy. Standard prefixes:

| Prefix | Examples | Purpose |
|---|---|---|
| `persona.*` | `persona.tone`, `persona.style`, `persona.role` | Agent's own character and voice |
| `relationship.user.*` | `relationship.user.name`, `relationship.user.timezone`, `relationship.user.preferences` | Facts about the primary user |
| `relationship.user.affect` | `relationship.user.affect` | Emotional/relational state (positive, neutral, strained) |
| `runtime.*` | `runtime.current_task`, `runtime.mode`, `runtime.last_tool` | Live operational state |
| `derived.*` | `derived.user.topics`, `derived.user.communication_style` | Inferred from evidence |
| `world.*` | `world.user.location`, `world.user.role`, `world.org` | Slow-moving contextual facts |

#### Bootstrap examples

A complete worked example is in [`examples/bootstrap_facets.sh`](examples/bootstrap_facets.sh). It seeds a fictional agent (Aria) with a fictional user (Alex) across all layers and namespaces — every facet is commented with why it exists. Copy it, replace the values, and run it.

```bash
export AGENTMEM_URL=http://localhost:3510
export AGENTMEM_TENANT=myagent
bash examples/bootstrap_facets.sh
```

The key facets to seed before your agent handles any turns:

```bash
# Minimum viable identity — without these, every response starts blind
am ingest facet persona.tone "warm, direct, and unhurried" --layer identity --confidence 1.0
am ingest facet persona.role "personal assistant" --layer identity --confidence 1.0
am ingest facet persona.style "concise; bullet points for lists" --layer identity --confidence 1.0
am ingest facet relationship.user.name "Alex" --layer identity --confidence 1.0
am ingest facet relationship.user.timezone "America/Chicago" --layer identity --confidence 1.0
am ingest facet relationship.user.communication_style "direct; prefers brevity" --layer identity --confidence 0.9
am ingest facet relationship.user.affect "positive" --layer identity --confidence 0.75
am ingest facet runtime.mode "assistant" --layer runtime --confidence 1.0
```

#### Querying facets

```bash
# All persona facets
am retrieve facets --tenant myagent --prefix persona.

# Everything about the user relationship
am retrieve facets --tenant myagent --prefix relationship.user.

# Only identity-layer facets
am retrieve facets --tenant myagent --layer identity
```

Facets are embedded to pgvector alongside evidence — `am retrieve semantic` will surface them when they match the query.

Facets support prefix queries: `am retrieve facets --prefix persona.` returns all persona facets.

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

**Step 1 — Before responding:** Pull and assemble context. See [Context injection](#context-injection) for the full philosophy and a Python assembly example. The quick version:

```bash
# Run all six lanes — order doesn't matter, they're independent
am retrieve facets --prefix persona. --prefix relationship.   # identity
am context get --max-age-seconds 3600                         # world state
am retrieve turns --conversation-id <id> --limit 20           # recent turns
am retrieve summary --verbatim-count 20 --limit 5             # rolling summary
am retrieve semantic --q "<current user message>" --limit 5   # semantic recall
am retrieve graph --limit 10                                  # graph recall
```

Inject into your system prompt in this order: identity → world state → recent turns → rolling summary → semantic recall → graph recall. Semantic search and identity facets are highest signal for most turns. Rolling summary becomes critical when the user references something from days or weeks ago.

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

agentmem handles storage, retrieval, and embedding. Your runtime layer adds:

- **Context assembly**: see [Context injection](#context-injection) — the Python `build_context()` example is a complete starting point
- **Token budgeting**: clip lanes by adjusting `limit` per lane; clip order is graph_recall → semantic_recall → rolling_summary → recent_turns → world_state → identity_facets (identity gets clipped last)
- **Echoes formatting**: `/retrieve/echoes` returns `word/word/word` triplet blocks; wrap them into natural-language persona phrases before injecting

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
