# ABOUTME: FastAPI application assembly — startup/shutdown lifecycle, adapter init, worker start.
# ABOUTME: Import this module's `app` object to run: uvicorn agentmem.service.app:app
"""FastAPI application factory for agentmem service."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from agentmem.service.config import AgentMemConfig

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle.

    Startup sequence:
      1. Load config (already done at module level)
      2. Initialize storage adapter → run migrate() (idempotent)
      3. Initialize embedding adapter
      4. Initialize event source adapters
      5. Construct all domain stores (inject adapters)
      6. Construct EventRouter; register default passthrough pattern ("*")
      7. Parse trigger strings → Trigger objects
      8. Construct WorkerCoordinator; register configured jobs; start()
      9. Attach domain services to app.state for use by route handlers

    Shutdown sequence:
      1. WorkerCoordinator.stop() — graceful drain
      2. Close event source adapters
      3. Close embedding adapter
      4. Close storage adapter
    """
    config: AgentMemConfig = app.state.config

    # 1. Storage adapter
    from agentmem.adapters.storage.postgres import PostgresStorageAdapter

    storage = PostgresStorageAdapter(dsn=config.storage.dsn)
    await storage.initialize()
    await storage.migrate()

    # 2. Embedding adapter
    if config.embeddings.backend == "ollama":
        from agentmem.adapters.embeddings.ollama import OllamaEmbeddingAdapter

        embedding = OllamaEmbeddingAdapter(
            url=config.embeddings.url,
            model=config.embeddings.model,
            dimensions=config.embeddings.dimensions,
        )
    else:
        from agentmem.adapters.embeddings.hash import HashEmbeddingAdapter

        embedding = HashEmbeddingAdapter()

    # 3. Event source adapters
    event_sources: dict[str, object] = {}
    # pg_listen source uses the same DSN as storage by default
    # (configured via workers.active_context trigger string referencing "pg_listen")

    # 4. Domain services
    from agentmem.core.active_context import ActiveContextStore
    from agentmem.core.digests import DigestEngine
    from agentmem.core.embeddings import EmbeddingService
    from agentmem.core.evidence import EvidenceLedger
    from agentmem.core.facets import FacetStore
    from agentmem.core.graph import GraphStore
    from agentmem.core.router import EventRouter

    emb_service = EmbeddingService(adapter=embedding, store=storage)
    evidence_ledger = EvidenceLedger(store=storage, vector_store=storage, embedding_service=emb_service)
    facet_store = FacetStore(store=storage)
    graph_store = GraphStore(store=storage)
    digest_engine = DigestEngine(store=storage, evidence_store=storage)
    active_context_store = ActiveContextStore(store=storage)

    # 5. Event router with default passthrough
    event_router = EventRouter()
    event_router.register("*", lambda e: str(e.payload))

    # 6. Parse triggers and build worker jobs
    from agentmem.workers.coordinator import JobContext, WorkerCoordinator
    from agentmem.workers.jobs.active_context import ActiveContextJob
    from agentmem.workers.jobs.digest import DigestGenerationJob
    from agentmem.workers.jobs.embed_reindex import EmbedReindexJob
    from agentmem.workers.jobs.retention import RetentionJob
    from agentmem.workers.triggers import parse_trigger

    job_context = JobContext(
        evidence_ledger=evidence_ledger,
        facet_store=facet_store,
        graph_store=graph_store,
        digest_engine=digest_engine,
        active_context_store=active_context_store,
        embedding_service=emb_service,
        event_router=event_router,
        config=config.model_dump(),
        _coordinator=None,  # type: ignore[arg-type]  # set below
        storage_adapter=storage,
    )

    coordinator = WorkerCoordinator(context=job_context)

    # Build event sources needed by continuous jobs
    workers_cfg = config.workers
    ac_cfg = workers_cfg.active_context
    ac_trigger = parse_trigger(ac_cfg.get("trigger", "continuous:pg_listen"))
    if hasattr(ac_trigger, "source") and ac_trigger.source == "pg_listen":
        from agentmem.adapters.events.pg_listen import PgListenAdapter

        pg_source = PgListenAdapter(dsn=config.storage.dsn)
        event_sources["pg_listen"] = pg_source

    coordinator._event_sources = event_sources

    # Register jobs
    er_cfg = workers_cfg.embed_reindex
    coordinator.register(EmbedReindexJob(
        batch_size=er_cfg.get("batch_size", 100),
        tenants=er_cfg.get("tenants"),
    ))

    d_cfg = workers_cfg.digest
    coordinator.register(DigestGenerationJob(
        types=d_cfg.get("types", ["daily", "weekly", "monthly"]),
    ))

    r_cfg = workers_cfg.retention
    coordinator.register(RetentionJob(
        evidence_days=r_cfg.get("evidence_days", 180),
    ))

    coordinator.register(ActiveContextJob())

    await coordinator.start()

    # 7. Attach to app.state for route handlers
    app.state.evidence_ledger = evidence_ledger
    app.state.facet_store = facet_store
    app.state.graph_store = graph_store
    app.state.digest_engine = digest_engine
    app.state.active_context_store = active_context_store
    app.state.embedding_service = emb_service
    app.state.event_router = event_router
    app.state.coordinator = coordinator
    app.state.storage = storage
    app.state.storage_adapter = storage

    logger.info("agentmem service started")

    yield

    # Shutdown
    await coordinator.stop()
    for source in event_sources.values():
        if hasattr(source, "disconnect"):
            await source.disconnect()
    await embedding.close()
    await storage.close()

    logger.info("agentmem service stopped")


def create_app(config: AgentMemConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Mounts API routers: ingest, retrieval, admin.
    WebhookAdapter router mounted at config.events mount_path if configured.
    """
    if config is None:
        config = AgentMemConfig()

    application = FastAPI(title="agentmem", lifespan=lifespan)
    application.state.config = config

    from agentmem.service.api.admin import router as admin_router
    from agentmem.service.api.admin import workers_router
    from agentmem.service.api.ingest import router as ingest_router
    from agentmem.service.api.retrieval import router as retrieval_router

    application.include_router(ingest_router)
    application.include_router(retrieval_router)
    application.include_router(admin_router)
    application.include_router(workers_router)

    return application


# Module-level app instance for uvicorn
app = create_app()
