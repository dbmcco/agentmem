# ABOUTME: PostgreSQL+pgvector storage adapter — the reference storage implementation.
# ABOUTME: Implements StorageAdapter + all six store protocols. Uses psycopg3 async pool.
"""PostgreSQL+pgvector storage adapter.

Implements: StorageAdapter, EvidenceStore, FacetStoreProtocol, GraphStoreProtocol,
            DigestStoreProtocol, ActiveContextStoreProtocol, VectorStore

Uses psycopg3 (psycopg[binary]>=3.1) with AsyncConnectionPool.
Parameter style: %s (NOT %(name)s — psycopg3 uses %s for positional parameters).

Schema (created by migrate(), idempotent):

    evidence (
        id          BIGSERIAL PRIMARY KEY,
        tenant_id   TEXT NOT NULL,
        event_type  TEXT NOT NULL,
        content     TEXT NOT NULL,
        occurred_at TIMESTAMPTZ NOT NULL,
        source_event_id TEXT,
        dedupe_key  TEXT NOT NULL UNIQUE,
        metadata    JSONB,
        channel_id  TEXT,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    )

    facets (
        id          BIGSERIAL PRIMARY KEY,
        tenant_id   TEXT NOT NULL,
        key         TEXT NOT NULL,
        value       TEXT NOT NULL,
        confidence  FLOAT DEFAULT 1.0,
        layer       TEXT DEFAULT 'searchable',
        updated_at  TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (tenant_id, key)
    )

    knowledge_graph (
        id          BIGSERIAL PRIMARY KEY,
        tenant_id   TEXT NOT NULL,
        subject     TEXT NOT NULL,
        predicate   TEXT NOT NULL,
        object      TEXT NOT NULL,
        confidence  FLOAT DEFAULT 1.0,
        source      TEXT,
        updated_at  TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (tenant_id, subject, predicate, object)
    )

    digests (
        id          BIGSERIAL PRIMARY KEY,
        tenant_id   TEXT NOT NULL,
        digest_type TEXT NOT NULL,
        period_start TIMESTAMPTZ NOT NULL,
        period_end  TIMESTAMPTZ NOT NULL,
        content     TEXT NOT NULL,
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (tenant_id, digest_type, period_start)
    )

    active_context (
        id          BIGSERIAL PRIMARY KEY,
        tenant_id   TEXT NOT NULL,
        section     TEXT NOT NULL,
        content     TEXT NOT NULL,
        updated_at  TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (tenant_id, section)
    )

    embeddings (
        id          BIGSERIAL PRIMARY KEY,
        tenant_id   TEXT NOT NULL,
        source_table TEXT NOT NULL,
        source_id   BIGINT NOT NULL,
        model_id    TEXT NOT NULL,
        embedding   vector(4096),
        collection  TEXT NOT NULL DEFAULT 'default',
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (source_table, source_id, model_id)
    )
    -- HNSW index: CREATE INDEX ON embeddings USING hnsw (embedding vector_cosine_ops)

    worker_jobs (
        name        TEXT PRIMARY KEY,
        last_run    TIMESTAMPTZ,
        last_error  TEXT,
        run_count   INT DEFAULT 0,
        heartbeat   TIMESTAMPTZ,
        state       TEXT DEFAULT 'idle'
    )
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from agentmem.core.models import (
        ContextSection,
        Digest,
        DigestFilters,
        EvidenceFilters,
        EvidenceRecord,
        FacetRecord,
        InsertResult,
        Triplet,
        VectorFilters,
        VectorRecord,
        VectorResult,
    )


class PostgresStorageAdapter:
    """PostgreSQL+pgvector storage adapter.

    A single class that implements all store protocols using one connection pool.
    Pass the same instance to all domain service constructors.

    Usage:
        adapter = PostgresStorageAdapter(dsn="postgresql://...")
        await adapter.initialize()
        await adapter.migrate()
        # pass as EvidenceStore, FacetStoreProtocol, etc.
    """

    def __init__(self, dsn: str, min_size: int = 2, max_size: int = 10) -> None:
        """Args:
            dsn:      PostgreSQL connection string
            min_size: minimum pool connections
            max_size: maximum pool connections
        """
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Open the connection pool. Must be called before any queries."""
        from psycopg_pool import AsyncConnectionPool

        self._pool = AsyncConnectionPool(
            self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
            open=False,
        )
        await self._pool.open()

    async def close(self) -> None:
        """Close the connection pool gracefully."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def migrate(self) -> None:
        """Create all tables and indexes idempotently (IF NOT EXISTS).

        Creates: evidence, facets, knowledge_graph, digests, active_context,
                 embeddings (with vector(4096) and HNSW index), worker_jobs.
        Also runs: CREATE EXTENSION IF NOT EXISTS vector
        """
        if not self._pool:
            raise RuntimeError("Pool not initialized - call initialize() first")

        async with self._pool.connection() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            # Evidence table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    occurred_at TIMESTAMPTZ NOT NULL,
                    source_event_id TEXT,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    metadata JSONB,
                    channel_id TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Facets table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS facets (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence FLOAT DEFAULT 1.0,
                    layer TEXT DEFAULT 'searchable',
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (tenant_id, key)
                )
            """)

            # Knowledge graph table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_graph (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    confidence FLOAT DEFAULT 1.0,
                    source TEXT,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (tenant_id, subject, predicate, object)
                )
            """)

            # Digests table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS digests (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    digest_type TEXT NOT NULL,
                    period_start TIMESTAMPTZ NOT NULL,
                    period_end TIMESTAMPTZ NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (tenant_id, digest_type, period_start)
                )
            """)

            # Active context table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS active_context (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    section TEXT NOT NULL,
                    content TEXT NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (tenant_id, section)
                )
            """)

            # Embeddings table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    source_table TEXT NOT NULL,
                    source_id BIGINT NOT NULL,
                    model_id TEXT NOT NULL,
                    embedding vector(4096),
                    collection TEXT NOT NULL DEFAULT 'default',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (source_table, source_id, model_id)
                )
            """)

            # HNSW index for embeddings
            # NOTE: not using CONCURRENTLY — it cannot run inside a transaction block.
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS embeddings_hnsw_idx
                ON embeddings USING hnsw (embedding vector_cosine_ops)
            """)

            # Worker jobs table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS worker_jobs (
                    name TEXT PRIMARY KEY,
                    last_run TIMESTAMPTZ,
                    last_error TEXT,
                    run_count INT DEFAULT 0,
                    heartbeat TIMESTAMPTZ,
                    state TEXT DEFAULT 'idle'
                )
            """)

            await conn.commit()

    # ── EvidenceStore ──────────────────────────────────────────────────────────

    async def insert(self, record: EvidenceRecord) -> InsertResult:
        """Insert evidence record. Returns InsertResult with deduplicated=True if dedupe_key exists.

        On conflict (dedupe_key), returns existing id and deduplicated=True without modifying row.
        embedding field is NOT stored in evidence table — caller routes to VectorStore separately.
        """
        from agentmem.core.models import InsertResult

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            # Atomic upsert: ON CONFLICT DO NOTHING avoids race conditions
            result = await conn.execute("""
                INSERT INTO evidence
                (tenant_id, event_type, content, occurred_at, source_event_id,
                 dedupe_key, metadata, channel_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dedupe_key) DO NOTHING
                RETURNING id
            """, (
                record.tenant_id, record.event_type, record.content,
                record.occurred_at, record.source_event_id,
                record.dedupe_key,
                json.dumps(record.metadata) if record.metadata else None,
                record.channel_id,
            ))

            row = await result.fetchone()
            if row:
                await conn.commit()
                return InsertResult(
                    id=row[0],
                    dedupe_key=record.dedupe_key,
                    deduplicated=False,
                )

            # Conflict: fetch existing id
            existing = await conn.execute(
                "SELECT id FROM evidence WHERE dedupe_key = %s",
                (record.dedupe_key,),
            )
            existing_row = await existing.fetchone()
            return InsertResult(
                id=existing_row[0] if existing_row else None,
                dedupe_key=record.dedupe_key,
                deduplicated=True,
            )

    async def query(self, filters: EvidenceFilters) -> list[EvidenceRecord]:
        """Query evidence rows matching filters.

        Filters applied: tenant_id (required), event_type, since (occurred_at >=),
                         channel_id, metadata_contains (JSONB @> operator), limit.
        Order: occurred_at DESC.
        """
        from agentmem.core.models import EvidenceRecord

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        where_clauses = ["tenant_id = %s"]
        params = [filters.tenant_id]

        if filters.event_type:
            where_clauses.append("event_type = %s")
            params.append(filters.event_type)

        if filters.since:
            where_clauses.append("occurred_at >= %s")
            params.append(filters.since)

        if filters.channel_id:
            where_clauses.append("channel_id = %s")
            params.append(filters.channel_id)

        if filters.metadata_contains:
            where_clauses.append("metadata @> %s")
            params.append(json.dumps(filters.metadata_contains))

        where_clause = " AND ".join(where_clauses)
        params.append(filters.limit)

        query = f"""
            SELECT id, tenant_id, event_type, content, occurred_at,
                   source_event_id, dedupe_key, metadata, channel_id
            FROM evidence
            WHERE {where_clause}
            ORDER BY occurred_at DESC
            LIMIT %s
        """

        async with self._pool.connection() as conn:
            result = await conn.execute(query, tuple(params))
            rows = await result.fetchall()

            records = []
            for row in rows:
                raw_meta = row[7]
                if raw_meta is None:
                    metadata = None
                elif isinstance(raw_meta, dict):
                    metadata = raw_meta
                else:
                    metadata = json.loads(raw_meta)
                records.append(EvidenceRecord(
                    id=row[0],
                    tenant_id=row[1],
                    event_type=row[2],
                    content=row[3],
                    occurred_at=row[4],
                    source_event_id=row[5],
                    dedupe_key=row[6],
                    metadata=metadata,
                    channel_id=row[8]
                ))

            return records

    # ── FacetStoreProtocol ─────────────────────────────────────────────────────

    async def set(self, record: FacetRecord) -> FacetRecord:
        """Upsert facet. On conflict (tenant_id, key) update value, confidence, layer, updated_at."""
        from agentmem.core.models import FacetRecord

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            result = await conn.execute("""
                INSERT INTO facets (tenant_id, key, value, confidence, layer)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, key)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    confidence = EXCLUDED.confidence,
                    layer = EXCLUDED.layer,
                    updated_at = NOW()
                RETURNING id, tenant_id, key, value, confidence, layer
            """, (
                record.tenant_id, record.key, record.value,
                record.confidence, record.layer
            ))

            row = await result.fetchone()
            if not row:
                raise RuntimeError("Failed to upsert facet")

            await conn.commit()
            return FacetRecord(
                id=row[0],
                tenant_id=row[1],
                key=row[2],
                value=row[3],
                confidence=row[4],
                layer=row[5]
            )

    async def get(self, tenant_id: str, key: str) -> FacetRecord | None:
        """Return facet by (tenant_id, key) or None."""
        from agentmem.core.models import FacetRecord

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            result = await conn.execute("""
                SELECT id, tenant_id, key, value, confidence, layer
                FROM facets
                WHERE tenant_id = %s AND key = %s
            """, (tenant_id, key))

            row = await result.fetchone()
            if not row:
                return None

            return FacetRecord(
                id=row[0],
                tenant_id=row[1],
                key=row[2],
                value=row[3],
                confidence=row[4],
                layer=row[5]
            )

    async def _list_facets(
        self,
        tenant_id: str,
        prefix: str | None,
        layer: str | None,
    ) -> list[FacetRecord]:
        """List facets for tenant. Optional key prefix filter (key LIKE prefix||'%') and layer filter."""
        from agentmem.core.models import FacetRecord

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        where_clauses = ["tenant_id = %s"]
        params = [tenant_id]

        if prefix:
            where_clauses.append("key LIKE %s")
            params.append(f"{prefix}%")

        if layer:
            where_clauses.append("layer = %s")
            params.append(layer)

        where_clause = " AND ".join(where_clauses)

        query = f"""
            SELECT id, tenant_id, key, value, confidence, layer
            FROM facets
            WHERE {where_clause}
            ORDER BY key
        """

        async with self._pool.connection() as conn:
            result = await conn.execute(query, tuple(params))
            rows = await result.fetchall()

            records = []
            for row in rows:
                records.append(FacetRecord(
                    id=row[0],
                    tenant_id=row[1],
                    key=row[2],
                    value=row[3],
                    confidence=row[4],
                    layer=row[5]
                ))

            return records

    async def list_multi(
        self,
        tenant_ids: list[str],
        prefix: str | None,
        layer: str | None,
    ) -> list[FacetRecord]:
        """List facets across multiple tenants (multi-tenant blending).
        Uses tenant_id = ANY(%s::text[]).
        """
        from agentmem.core.models import FacetRecord

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        if not tenant_ids:
            return []

        where_clauses = ["tenant_id = ANY(%s::text[])"]
        params = [tenant_ids]

        if prefix:
            where_clauses.append("key LIKE %s")
            params.append(f"{prefix}%")

        if layer:
            where_clauses.append("layer = %s")
            params.append(layer)

        where_clause = " AND ".join(where_clauses)

        query = f"""
            SELECT id, tenant_id, key, value, confidence, layer
            FROM facets
            WHERE {where_clause}
            ORDER BY tenant_id, key
        """

        async with self._pool.connection() as conn:
            result = await conn.execute(query, tuple(params))
            rows = await result.fetchall()

            records = []
            for row in rows:
                records.append(FacetRecord(
                    id=row[0],
                    tenant_id=row[1],
                    key=row[2],
                    value=row[3],
                    confidence=row[4],
                    layer=row[5]
                ))

            return records

    async def _delete_facet(self, tenant_id: str, key: str) -> bool:
        """Delete facet. Returns True if row was deleted."""
        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            result = await conn.execute("""
                DELETE FROM facets
                WHERE tenant_id = %s AND key = %s
            """, (tenant_id, key))

            await conn.commit()
            return result.rowcount > 0

    # ── GraphStoreProtocol ─────────────────────────────────────────────────────

    async def add(self, triplet: Triplet) -> Triplet:
        """Upsert triplet. On conflict (tenant_id, subject, predicate, object) update confidence, source, updated_at."""
        from agentmem.core.models import Triplet

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            result = await conn.execute("""
                INSERT INTO knowledge_graph (tenant_id, subject, predicate, object, confidence, source)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, subject, predicate, object)
                DO UPDATE SET
                    confidence = EXCLUDED.confidence,
                    source = EXCLUDED.source,
                    updated_at = NOW()
                RETURNING id, tenant_id, subject, predicate, object, confidence, source
            """, (
                triplet.tenant_id, triplet.subject, triplet.predicate,
                triplet.object, triplet.confidence, triplet.source
            ))

            row = await result.fetchone()
            if not row:
                raise RuntimeError("Failed to upsert triplet")

            await conn.commit()
            return Triplet(
                id=row[0],
                tenant_id=row[1],
                subject=row[2],
                predicate=row[3],
                object=row[4],
                confidence=row[5],
                source=row[6]
            )

    async def query_subject(self, tenant_id: str, subject: str) -> list[Triplet]:
        from agentmem.core.models import Triplet

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            result = await conn.execute("""
                SELECT id, tenant_id, subject, predicate, object, confidence, source
                FROM knowledge_graph
                WHERE tenant_id = %s AND subject = %s
            """, (tenant_id, subject))

            rows = await result.fetchall()
            triplets = []
            for row in rows:
                triplets.append(Triplet(
                    id=row[0],
                    tenant_id=row[1],
                    subject=row[2],
                    predicate=row[3],
                    object=row[4],
                    confidence=row[5],
                    source=row[6]
                ))

            return triplets

    async def query_object(self, tenant_id: str, object_: str) -> list[Triplet]:
        from agentmem.core.models import Triplet

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            result = await conn.execute("""
                SELECT id, tenant_id, subject, predicate, object, confidence, source
                FROM knowledge_graph
                WHERE tenant_id = %s AND object = %s
            """, (tenant_id, object_))

            rows = await result.fetchall()
            triplets = []
            for row in rows:
                triplets.append(Triplet(
                    id=row[0],
                    tenant_id=row[1],
                    subject=row[2],
                    predicate=row[3],
                    object=row[4],
                    confidence=row[5],
                    source=row[6]
                ))

            return triplets

    async def query_predicate(self, tenant_id: str, predicate: str) -> list[Triplet]:
        from agentmem.core.models import Triplet

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            result = await conn.execute("""
                SELECT id, tenant_id, subject, predicate, object, confidence, source
                FROM knowledge_graph
                WHERE tenant_id = %s AND predicate = %s
            """, (tenant_id, predicate))

            rows = await result.fetchall()
            triplets = []
            for row in rows:
                triplets.append(Triplet(
                    id=row[0],
                    tenant_id=row[1],
                    subject=row[2],
                    predicate=row[3],
                    object=row[4],
                    confidence=row[5],
                    source=row[6]
                ))

            return triplets

    # ── DigestStoreProtocol ────────────────────────────────────────────────────

    async def _upsert_digest(self, digest: Digest) -> Digest:
        """Upsert digest. On conflict (tenant_id, digest_type, period_start) update content."""
        from agentmem.core.models import Digest

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            result = await conn.execute("""
                INSERT INTO digests (tenant_id, digest_type, period_start, period_end, content)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, digest_type, period_start)
                DO UPDATE SET content = EXCLUDED.content
                RETURNING id, tenant_id, digest_type, period_start, period_end, content
            """, (
                digest.tenant_id, digest.digest_type, digest.period_start,
                digest.period_end, digest.content
            ))

            row = await result.fetchone()
            if not row:
                raise RuntimeError("Failed to upsert digest")

            await conn.commit()
            return Digest(
                id=row[0],
                tenant_id=row[1],
                digest_type=row[2],
                period_start=row[3],
                period_end=row[4],
                content=row[5]
            )

    async def _list_digests(self, filters: DigestFilters) -> list[Digest]:
        """List digests matching filters. Order: period_start DESC, limit applied."""
        from agentmem.core.models import Digest

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        where_clauses = ["tenant_id = %s"]
        params = [filters.tenant_id]

        if filters.digest_type:
            where_clauses.append("digest_type = %s")
            params.append(filters.digest_type)

        if filters.period_start:
            where_clauses.append("period_start >= %s")
            params.append(filters.period_start)

        if filters.period_end:
            where_clauses.append("period_end <= %s")
            params.append(filters.period_end)

        where_clause = " AND ".join(where_clauses)
        params.append(filters.limit)

        query = f"""
            SELECT id, tenant_id, digest_type, period_start, period_end, content
            FROM digests
            WHERE {where_clause}
            ORDER BY period_start DESC
            LIMIT %s
        """

        async with self._pool.connection() as conn:
            result = await conn.execute(query, tuple(params))
            rows = await result.fetchall()

            digests = []
            for row in rows:
                digests.append(Digest(
                    id=row[0],
                    tenant_id=row[1],
                    digest_type=row[2],
                    period_start=row[3],
                    period_end=row[4],
                    content=row[5]
                ))

            return digests

    # ── ActiveContextStoreProtocol ─────────────────────────────────────────────

    async def _upsert_context(self, section: ContextSection) -> ContextSection:
        """Upsert active context section. On conflict (tenant_id, section) update content, updated_at."""
        from agentmem.core.models import ContextSection

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            result = await conn.execute("""
                INSERT INTO active_context (tenant_id, section, content, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (tenant_id, section)
                DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
                RETURNING id, tenant_id, section, content, updated_at
            """, (section.tenant_id, section.section, section.content))

            row = await result.fetchone()
            if not row:
                raise RuntimeError("Failed to upsert context section")

            await conn.commit()
            return ContextSection(
                id=row[0],
                tenant_id=row[1],
                section=row[2],
                content=row[3],
                updated_at=row[4]
            )

    async def get_all(
        self,
        tenant_id: str,
        max_age_seconds: float | None,
    ) -> list[ContextSection]:
        """Return all sections for tenant. If max_age_seconds set, filter updated_at >= NOW() - interval."""
        from agentmem.core.models import ContextSection

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        where_clauses = ["tenant_id = %s"]
        params = [tenant_id]

        if max_age_seconds:
            where_clauses.append("updated_at >= NOW() - %s * interval '1 second'")
            params.append(max_age_seconds)

        where_clause = " AND ".join(where_clauses)

        query = f"""
            SELECT id, tenant_id, section, content, updated_at
            FROM active_context
            WHERE {where_clause}
            ORDER BY updated_at DESC
        """

        async with self._pool.connection() as conn:
            result = await conn.execute(query, tuple(params))
            rows = await result.fetchall()

            sections = []
            for row in rows:
                sections.append(ContextSection(
                    id=row[0],
                    tenant_id=row[1],
                    section=row[2],
                    content=row[3],
                    updated_at=row[4]
                ))

            return sections

    async def _delete_context(self, tenant_id: str, section: str) -> bool:
        """Delete context section. Returns True if deleted."""
        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            result = await conn.execute("""
                DELETE FROM active_context
                WHERE tenant_id = %s AND section = %s
            """, (tenant_id, section))

            await conn.commit()
            return result.rowcount > 0

    # ── Dispatch methods (resolve protocol name collisions) ─────────────────

    async def upsert(self, obj: Any) -> Any:
        """Dispatch upsert to the correct store based on argument type."""
        from agentmem.core.models import Digest, ContextSection

        if isinstance(obj, Digest):
            return await self._upsert_digest(obj)
        if isinstance(obj, ContextSection):
            return await self._upsert_context(obj)
        raise TypeError(f"upsert() expects Digest or ContextSection, got {type(obj).__name__}")

    async def list(self, *args: Any, **kwargs: Any) -> Any:
        """Dispatch list to facets (3-arg form) or digests (DigestFilters form)."""
        from agentmem.core.models import DigestFilters

        if args and isinstance(args[0], DigestFilters):
            return await self._list_digests(args[0])
        # FacetStoreProtocol.list(tenant_id, prefix, layer)
        return await self._list_facets(*args, **kwargs)

    async def delete(self, tenant_id: str, key_or_section: str) -> bool:
        """Dispatch delete: tries facets first, then active_context."""
        if not self._pool:
            raise RuntimeError("Pool not initialized")
        async with self._pool.connection() as conn:
            r = await conn.execute(
                "DELETE FROM facets WHERE tenant_id = %s AND key = %s",
                (tenant_id, key_or_section),
            )
            if r.rowcount > 0:
                await conn.commit()
                return True
            r = await conn.execute(
                "DELETE FROM active_context WHERE tenant_id = %s AND section = %s",
                (tenant_id, key_or_section),
            )
            await conn.commit()
            return r.rowcount > 0

    # ── VectorStore ────────────────────────────────────────────────────────────

    async def store(self, record: VectorRecord) -> None:
        """Store or update a vector embedding.

        On conflict (source_table, source_id, model_id) update embedding and collection.
        Vector dimension must match the column definition (4096).
        Use pgvector's list-to-vector cast: %s::vector
        """
        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            await conn.execute("""
                INSERT INTO embeddings (tenant_id, source_table, source_id, model_id, embedding, collection)
                VALUES (%s, %s, %s, %s, %s::vector, %s)
                ON CONFLICT (source_table, source_id, model_id)
                DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    collection = EXCLUDED.collection
            """, (
                record.tenant_id, record.source_table, record.source_id,
                record.model_id, record.embedding, record.collection
            ))

            await conn.commit()

    async def search(
        self,
        query: list[float],
        filters: VectorFilters,
    ) -> list[VectorResult]:
        """Cosine similarity search using HNSW index.

        Returns VectorResult list ordered by similarity DESC (score = 1 - cosine_distance).
        Filter by: tenant_id (required), source_table, collection, channel_id (joined from evidence),
                   extra_tenant_ids (tenant_id = ANY(%s::text[])).

        SQL pattern:
          SELECT e.source_table, e.source_id, e.tenant_id,
                 1 - (e.embedding <=> %s::vector) AS score,
                 <content from joined table>
          FROM embeddings e
          LEFT JOIN evidence ev ON e.source_table='evidence' AND e.source_id=ev.id
          LEFT JOIN facets f ON e.source_table='facets' AND e.source_id=f.id
          WHERE (e.tenant_id=%s OR e.tenant_id = ANY(%s::text[]))
            [AND e.source_table=%s]
            [AND e.collection=%s]
          ORDER BY e.embedding <=> %s::vector
          LIMIT %s
        """
        from agentmem.core.models import VectorResult

        if not self._pool:
            raise RuntimeError("Pool not initialized")

        # Build WHERE clause
        where_clauses = []
        params = []

        # Add query vector parameter for SELECT clause
        params.append(query)

        # Tenant filtering (required + extra)
        tenant_list = [filters.tenant_id] + filters.extra_tenant_ids
        if len(tenant_list) == 1:
            where_clauses.append("e.tenant_id = %s")
            params.append(filters.tenant_id)
        else:
            where_clauses.append("e.tenant_id = ANY(%s::text[])")
            params.append(tenant_list)

        # Optional filters
        if filters.source_table:
            where_clauses.append("e.source_table = %s")
            params.append(filters.source_table)

        if filters.collection:
            where_clauses.append("e.collection = %s")
            params.append(filters.collection)

        if filters.channel_id:
            where_clauses.append("ev.channel_id = %s")
            params.append(filters.channel_id)

        where_clause = " AND ".join(where_clauses)

        # Add parameters for ORDER BY and LIMIT
        params.append(query)  # For ORDER BY
        params.append(filters.limit)

        query_sql = f"""
            SELECT e.source_table, e.source_id, e.tenant_id,
                   1 - (e.embedding <=> %s::vector) AS score,
                   COALESCE(ev.content, f.value) AS content
            FROM embeddings e
            LEFT JOIN evidence ev ON e.source_table = 'evidence' AND e.source_id = ev.id
            LEFT JOIN facets f ON e.source_table = 'facets' AND e.source_id = f.id
            WHERE {where_clause}
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
        """

        async with self._pool.connection() as conn:
            result = await conn.execute(query_sql, tuple(params))
            rows = await result.fetchall()

            results = []
            for row in rows:
                results.append(VectorResult(
                    source_table=row[0],
                    source_id=row[1],
                    tenant_id=row[2],
                    score=float(row[3]),
                    content=row[4] or ""
                ))

            return results

    async def reindex(
        self,
        source_table: str,
        tenant_id: str | None,
        limit: int = 100,
    ) -> int:
        """Return count of source rows that have no VectorStore entry for current model.

        Caller (EmbedReindexJob) uses this to discover what needs embedding.
        This method returns the IDs; the job calls EmbeddingService.embed_and_store for each.

        NOTE: This method is called reindex but it only IDENTIFIES orphaned rows.
        The actual embedding is done by EmbedReindexJob via EmbeddingService.
        Returns: count of rows needing embedding (capped by limit).
        """
        if not self._pool:
            raise RuntimeError("Pool not initialized")

        if source_table not in ("evidence", "facets"):
            raise ValueError(f"Invalid source_table: {source_table}")

        where_clauses: list[str] = []
        params: list[Any] = [source_table]

        if tenant_id:
            where_clauses.append("s.tenant_id = %s")
            params.append(tenant_id)

        outer_filter = ""
        if where_clauses:
            outer_filter = " AND " + " AND ".join(where_clauses)

        # Count rows in source table that don't have embeddings
        # Uses NOT EXISTS (correlated subquery) to avoid duplicate param issue
        query = f"""
            SELECT COUNT(*) FROM (
                SELECT s.id
                FROM {source_table} s
                WHERE NOT EXISTS (
                    SELECT 1 FROM embeddings e
                    WHERE e.source_table = %s AND e.source_id = s.id
                ){outer_filter}
                LIMIT %s
            ) sub
        """
        params.append(limit)

        async with self._pool.connection() as conn:
            result = await conn.execute(query, tuple(params))
            row = await result.fetchone()
            return row[0] if row else 0

    # ── Worker job state ───────────────────────────────────────────────────────

    async def get_job_state(self, name: str) -> dict[str, Any] | None:
        """Return worker job state dict or None if not found."""
        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            result = await conn.execute("""
                SELECT name, last_run, last_error, run_count, heartbeat, state
                FROM worker_jobs
                WHERE name = %s
            """, (name,))

            row = await result.fetchone()
            if not row:
                return None

            return {
                "name": row[0],
                "last_run": row[1],
                "last_error": row[2],
                "run_count": row[3],
                "heartbeat": row[4],
                "state": row[5]
            }

    async def upsert_job_state(
        self,
        name: str,
        last_run: datetime | None = None,
        last_error: str | None = None,
        run_count: int | None = None,
        heartbeat: datetime | None = None,
        state: str | None = None,
    ) -> None:
        """Upsert job state row.

        On conflict (name), only update the columns that were explicitly passed
        (non-None). On fresh insert, columns default to their schema defaults.
        """
        if not self._pool:
            raise RuntimeError("Pool not initialized")

        async with self._pool.connection() as conn:
            # Build dynamic SET clause for non-None params
            update_fields = []
            update_params: list[Any] = []

            if last_run is not None:
                update_fields.append("last_run = %s")
                update_params.append(last_run)
            if last_error is not None:
                update_fields.append("last_error = %s")
                update_params.append(last_error)
            if run_count is not None:
                update_fields.append("run_count = %s")
                update_params.append(run_count)
            if heartbeat is not None:
                update_fields.append("heartbeat = %s")
                update_params.append(heartbeat)
            if state is not None:
                update_fields.append("state = %s")
                update_params.append(state)

            if not update_fields:
                # No fields to update — ensure the row exists with defaults
                await conn.execute(
                    "INSERT INTO worker_jobs (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                    (name,),
                )
            else:
                # Build matching INSERT columns/values for the non-None fields
                col_names = ["name"]
                insert_params: list[Any] = [name]

                if last_run is not None:
                    col_names.append("last_run")
                    insert_params.append(last_run)
                if last_error is not None:
                    col_names.append("last_error")
                    insert_params.append(last_error)
                if run_count is not None:
                    col_names.append("run_count")
                    insert_params.append(run_count)
                if heartbeat is not None:
                    col_names.append("heartbeat")
                    insert_params.append(heartbeat)
                if state is not None:
                    col_names.append("state")
                    insert_params.append(state)

                cols = ", ".join(col_names)
                placeholders = ", ".join(["%s"] * len(col_names))
                update_clause = ", ".join(update_fields)

                await conn.execute(
                    f"INSERT INTO worker_jobs ({cols}) VALUES ({placeholders}) "
                    f"ON CONFLICT (name) DO UPDATE SET {update_clause}",
                    tuple(insert_params + update_params),
                )

            await conn.commit()
