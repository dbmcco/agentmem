# ABOUTME: Tests for the WorkerCoordinator.
# ABOUTME: Verifies job scheduling, execution, and state persistence.
"""Tests for the WorkerCoordinator."""

from datetime import timedelta

from agentmem.adapters.storage import MemoryJobStore
from agentmem.workers.coordinator import WorkerCoordinator


async def test_register_and_run_once():
    store = MemoryJobStore()
    coord = WorkerCoordinator(job_store=store)
    ran = False

    async def job() -> None:
        nonlocal ran
        ran = True

    coord.register("test_job", job, interval=timedelta(seconds=60))
    await coord.run_once("test_job")
    assert ran is True

    state = await store.get_state("test_job")
    assert state is not None
    assert state.status == "idle"
    assert state.last_run is not None


async def test_run_once_captures_failure():
    store = MemoryJobStore()
    coord = WorkerCoordinator(job_store=store)

    async def failing_job() -> None:
        raise ValueError("boom")

    coord.register("fail_job", failing_job)
    await coord.run_once("fail_job")

    state = await store.get_state("fail_job")
    assert state is not None
    assert state.status == "failed"
    assert state.error == "boom"
