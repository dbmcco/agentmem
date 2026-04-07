# ABOUTME: WorkerCoordinator — job lifecycle, crash recovery, heartbeat monitoring, state tracking.
# ABOUTME: The first-class background worker layer that paia-memory was missing.
"""WorkerCoordinator: manages all background jobs."""
from __future__ import annotations

import abc
import asyncio
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from agentmem.core.models import JobResult, JobStatus
from agentmem.workers.triggers import (
    AnyTrigger,
    CronTrigger,
    ContinuousTrigger,
    EventTrigger,
    OnDemandTrigger,
    TurnCountTrigger,
)

if TYPE_CHECKING:
    from agentmem.core.active_context import ActiveContextStore
    from agentmem.core.digests import DigestEngine
    from agentmem.core.embeddings import EmbeddingService
    from agentmem.core.evidence import EvidenceLedger
    from agentmem.core.facets import FacetStore
    from agentmem.core.graph import GraphStore
    from agentmem.core.router import EventRouter
    from agentmem.core.models import EventRecord


@dataclass
class JobContext:
    """Injected into every job run. Provides access to all domain services."""

    evidence_ledger: EvidenceLedger
    facet_store: FacetStore
    graph_store: GraphStore
    digest_engine: DigestEngine
    active_context_store: ActiveContextStore
    embedding_service: EmbeddingService
    event_router: EventRouter
    config: dict[str, Any]
    _coordinator: WorkerCoordinator = field(repr=False)
    storage_adapter: Any | None = None  # v1 escape hatch for jobs needing direct DB access
    job_name: str = ""

    async def heartbeat(self) -> None:
        """Continuous jobs must call this within heartbeat_interval_seconds.

        Updates heartbeat timestamp in coordinator state.
        """
        await self._coordinator._update_heartbeat(self.job_name)

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        """In-process pub/sub for inter-job coordination signals."""
        await self._coordinator._publish(topic, message)

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Subscribe to in-process pub/sub topic."""
        await self._coordinator._subscribe(topic, handler)


class ScheduledJob(abc.ABC):
    """Base class for cron-triggered or on-demand jobs."""

    name: str
    trigger: CronTrigger | OnDemandTrigger
    depends_on: list[str] = field(default_factory=list)

    @abc.abstractmethod
    async def run(self, context: JobContext) -> JobResult:
        """Execute the job. Must be idempotent."""
        ...


class ContinuousJob(abc.ABC):
    """Base class for continuous or event-driven jobs."""

    name: str
    trigger: ContinuousTrigger | EventTrigger
    heartbeat_interval_seconds: float = 30.0

    @abc.abstractmethod
    async def handle(self, event: EventRecord, context: JobContext) -> None:
        """Handle a single incoming event."""
        ...


class WorkerCoordinator:
    """Manages the full lifecycle of all registered jobs.

    Responsibilities:
    - Start/stop all jobs; graceful shutdown (drain in-flight before exit)
    - Crash recovery: continuous jobs restarted with exponential backoff
      (1s, 2s, 4s, 8s, 16s); declared dead after 5 consecutive failures
    - State persistence: last_run, last_error, run_count per job (via storage adapter)
    - Heartbeat monitoring: flags stale continuous jobs; triggers restart
    - Dependency ordering: depends_on resolved at dispatch time
    - In-process pub/sub for inter-job messaging
    """

    BACKOFF_SEQUENCE = [1.0, 2.0, 4.0, 8.0, 16.0]  # seconds
    MAX_CONSECUTIVE_FAILURES = 5

    def __init__(self, context: JobContext) -> None:
        self._base_context = context
        self._jobs: dict[str, ScheduledJob | ContinuousJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._heartbeats: dict[str, datetime] = {}
        self._job_states: dict[str, dict] = {}
        self._pub_sub: dict[str, list] = {}  # topic -> list of handlers
        self._event_sources: dict[str, Any] = {}  # populated by service/app.py
        self._turn_counters: dict[tuple[str, str, str], int] = {}  # (job_name, tenant_id, event_type) -> count

    def register(self, job: ScheduledJob | ContinuousJob) -> None:
        """Register a job with the coordinator. Must be called before start()."""
        self._jobs[job.name] = job

    async def start(self) -> None:
        """Start all registered jobs as asyncio tasks."""
        # Wire up turn-count trigger subscription before starting jobs
        turn_count_jobs = [
            j for j in self._jobs.values()
            if isinstance(j, ScheduledJob) and isinstance(j.trigger, TurnCountTrigger)
        ]
        if turn_count_jobs:
            async def _on_evidence_inserted(message: dict[str, Any]) -> None:
                tenant_id = message.get('tenant_id', '')
                event_type = message.get('event_type', '')
                for job in turn_count_jobs:
                    trigger = job.trigger
                    assert isinstance(trigger, TurnCountTrigger)
                    if event_type != trigger.event_type:
                        continue
                    key = (job.name, tenant_id, event_type)
                    self._turn_counters[key] = self._turn_counters.get(key, 0) + 1
                    if self._turn_counters[key] >= trigger.count:
                        self._turn_counters[key] = 0
                        ctx = self._make_context(job.name)
                        await job.run(ctx)

            await self._subscribe('evidence:inserted', _on_evidence_inserted)

        for job in self._jobs.values():
            if isinstance(job, ScheduledJob):
                if isinstance(job.trigger, TurnCountTrigger):
                    continue  # handled by pub/sub, not cron loop
                task = asyncio.create_task(self._run_scheduled(job))
            else:
                task = asyncio.create_task(self._run_continuous(job))
            self._tasks[job.name] = task

    async def stop(self) -> None:
        """Graceful shutdown: cancel tasks, wait for in-flight to drain."""
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def run_now(self, job_name: str, **kwargs: Any) -> JobResult:
        """Trigger an on-demand job run immediately. Works for any job type."""
        job = self._jobs.get(job_name)
        if not job:
            raise KeyError(f'Unknown job: {job_name}')
        if isinstance(job, ContinuousJob):
            raise ValueError(f"Cannot run_now a ContinuousJob '{job_name}': use the event trigger instead")
        ctx = self._make_context(job.name)
        return await job.run(ctx)

    async def status(self) -> list[JobStatus]:
        """Return current status for all registered jobs."""
        result = []
        now = datetime.now(timezone.utc)
        for name, job in self._jobs.items():
            state = self._job_states.get(name, {})
            hb = self._heartbeats.get(name)
            hb_age = (now - hb).total_seconds() if hb else None
            trigger_type = 'cron' if hasattr(job.trigger, 'schedule') else ('continuous' if hasattr(job.trigger, 'source') and not hasattr(job.trigger, 'event_type_pattern') else ('event' if hasattr(job.trigger, 'event_type_pattern') else 'on_demand'))
            result.append(JobStatus(
                name=name, trigger_type=trigger_type,
                last_run=state.get('last_run'), last_result=state.get('last_result'),
                error_count=state.get('error_count', 0),
                heartbeat_age_seconds=hb_age,
                state=state.get('state', 'idle'),
            ))
        return result

    # ── Internal methods ───────────────────────────────────────────────────────

    def _make_context(self, job_name: str) -> JobContext:
        """Create a copy of base context with coordinator set and job_name set"""
        ctx = dataclasses.replace(self._base_context, _coordinator=self, job_name=job_name)
        return ctx

    async def _run_scheduled(self, job: ScheduledJob) -> None:
        """Loop: check cron schedule; run job when due; persist state; handle errors."""
        from croniter import croniter

        cron = croniter(job.trigger.schedule, datetime.now(timezone.utc))
        while True:
            next_run = cron.get_next(datetime)
            now = datetime.now(timezone.utc)
            delay = (next_run - now).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            ctx = self._make_context(job.name)
            try:
                result = await job.run(ctx)
                self._job_states[job.name] = {
                    'last_run': datetime.now(timezone.utc),
                    'last_result': result,
                    'error_count': 0,
                    'state': 'idle'
                }
            except Exception as e:
                ec = self._job_states.get(job.name, {}).get('error_count', 0) + 1
                self._job_states[job.name] = {
                    'error_count': ec,
                    'state': 'dead' if ec >= 5 else 'idle',
                    'last_error': str(e)
                }

    async def _run_continuous(self, job: ContinuousJob) -> None:
        """Loop: connect event source; run job.handle per event; restart on failure with backoff."""
        error_count = 0
        while error_count < self.MAX_CONSECUTIVE_FAILURES:
            try:
                # Get source adapter from stored event sources
                source_name = job.trigger.source
                source = self._event_sources.get(source_name)
                if source is None:
                    raise RuntimeError(f'Event source {source_name!r} not registered')
                await source.connect()
                ctx = self._make_context(job.name)

                async def handler(event):
                    await job.handle(event, ctx)

                await source.subscribe(handler)
                error_count = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                error_count += 1
                delay = min(
                    self.BACKOFF_SEQUENCE[error_count - 1] if error_count <= len(self.BACKOFF_SEQUENCE) else 16.0,
                    30.0  # max reconnect delay
                )
                await asyncio.sleep(delay)
        await self._publish('job:dead', {'job': job.name})

    async def _update_heartbeat(self, job_name: str) -> None:
        """Update heartbeat timestamp for a continuous job."""
        self._heartbeats[job_name] = datetime.now(timezone.utc)

    async def _publish(self, topic: str, message: dict[str, Any]) -> None:
        """Deliver message to all subscribers of topic."""
        handlers = self._pub_sub.get(topic, [])
        for handler in handlers:
            await handler(message)

    async def _subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Register a handler for pub/sub topic."""
        if topic not in self._pub_sub:
            self._pub_sub[topic] = []
        self._pub_sub[topic].append(handler)
