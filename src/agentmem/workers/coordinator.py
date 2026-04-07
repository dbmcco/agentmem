# ABOUTME: Worker coordinator for background job scheduling.
# ABOUTME: Manages and runs periodic jobs like embedding reindex and retention.
"""Worker coordinator — runs background jobs on schedule.

Persists job state to storage (not in-memory only per spec).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from agentmem.core.models import JobState
from agentmem.core.protocols import JobStore

logger = logging.getLogger(__name__)

JobFn = Callable[[], Awaitable[None]]


class WorkerCoordinator:
    """Runs registered jobs on a configurable interval."""

    def __init__(self, job_store: JobStore) -> None:
        self._job_store = job_store
        self._jobs: dict[str, tuple[JobFn, timedelta]] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def register(
        self, name: str, fn: JobFn, interval: timedelta = timedelta(minutes=5)
    ) -> None:
        self._jobs[name] = (fn, interval)

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def run_once(self, name: str) -> None:
        """Run a single job immediately."""
        if name not in self._jobs:
            raise KeyError(f"Unknown job: {name}")
        fn, _ = self._jobs[name]
        state = await self._job_store.get_state(name) or JobState(name=name)
        state.status = "running"
        await self._job_store.put_state(state)
        try:
            await fn()
            state.status = "idle"
            state.last_run = datetime.now(UTC)
            state.error = None
        except Exception as exc:
            state.status = "failed"
            state.error = str(exc)
            logger.exception("Job %s failed", name)
        await self._job_store.put_state(state)

    async def _loop(self) -> None:
        while self._running:
            now = datetime.now(UTC)
            for name, (fn, interval) in self._jobs.items():
                state = await self._job_store.get_state(name) or JobState(name=name)
                if state.status == "running":
                    continue
                if state.last_run and (now - state.last_run) < interval:
                    continue
                state.status = "running"
                await self._job_store.put_state(state)
                try:
                    await fn()
                    state.status = "idle"
                    state.last_run = now
                    state.error = None
                except Exception as exc:
                    state.status = "failed"
                    state.error = str(exc)
                    logger.exception("Job %s failed", name)
                await self._job_store.put_state(state)
            await asyncio.sleep(1)
