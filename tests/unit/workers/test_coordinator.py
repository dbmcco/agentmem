# ABOUTME: Tests for the WorkerCoordinator.
# ABOUTME: Verifies job scheduling, execution, and state persistence.
"""Tests for the WorkerCoordinator."""
import asyncio
from dataclasses import dataclass, field

import pytest

from agentmem.core.models import JobResult, JobStatus
from agentmem.workers.coordinator import JobContext, ScheduledJob, ContinuousJob, WorkerCoordinator
from agentmem.workers.triggers import OnDemandTrigger, ContinuousTrigger


@dataclass
class MockJob(ScheduledJob):
    """Mock job for testing."""

    name: str = "test_job"
    trigger: OnDemandTrigger = field(default_factory=OnDemandTrigger)
    run_count: int = 0

    async def run(self, context: JobContext) -> JobResult:
        self.run_count += 1
        return JobResult(success=True, items_processed=1)


@dataclass
class MockContinuousJob(ContinuousJob):
    """Mock continuous job for testing."""

    name: str = "test_continuous_job"
    trigger: ContinuousTrigger = field(default_factory=lambda: ContinuousTrigger(source="test_source"))
    handle_count: int = 0

    async def handle(self, event, context: JobContext) -> None:
        self.handle_count += 1


@pytest.fixture
def mock_context():
    """Create a mock JobContext for testing."""
    return JobContext(
        evidence_ledger=None,  # type: ignore
        facet_store=None,  # type: ignore
        graph_store=None,  # type: ignore
        digest_engine=None,  # type: ignore
        active_context_store=None,  # type: ignore
        embedding_service=None,  # type: ignore
        event_router=None,  # type: ignore
        config={},
        _coordinator=None,  # type: ignore
        job_name="",
    )


async def test_register_and_status(mock_context):
    """Test registering a job and checking status."""
    coordinator = WorkerCoordinator(mock_context)
    job = MockJob()

    coordinator.register(job)
    statuses = await coordinator.status()

    assert len(statuses) == 1
    status = statuses[0]
    assert status.name == "test_job"
    assert status.trigger_type == "on_demand"
    assert status.last_run is None
    assert status.error_count == 0
    assert status.state == "idle"


async def test_run_now_on_demand_job(mock_context):
    """Test run_now calls job.run and returns JobResult."""
    coordinator = WorkerCoordinator(mock_context)
    job = MockJob()

    coordinator.register(job)
    result = await coordinator.run_now("test_job")

    assert result.success is True
    assert result.items_processed == 1
    assert job.run_count == 1


async def test_run_now_unknown_job(mock_context):
    """Test run_now raises KeyError for unknown job."""
    coordinator = WorkerCoordinator(mock_context)

    with pytest.raises(KeyError, match="Unknown job: nonexistent"):
        await coordinator.run_now("nonexistent")


async def test_run_now_continuous_job_raises_error(mock_context):
    """Test run_now raises ValueError when called with ContinuousJob."""
    coordinator = WorkerCoordinator(mock_context)
    job = MockContinuousJob()

    coordinator.register(job)

    with pytest.raises(ValueError, match="Cannot run_now a ContinuousJob 'test_continuous_job': use the event trigger instead"):
        await coordinator.run_now("test_continuous_job")


async def test_run_now_scheduled_job_works(mock_context):
    """Test run_now works correctly for ScheduledJob."""
    coordinator = WorkerCoordinator(mock_context)
    job = MockJob()

    coordinator.register(job)
    result = await coordinator.run_now("test_job")

    assert result.success is True
    assert result.items_processed == 1
    assert job.run_count == 1


async def test_pubsub_publish_delivers(mock_context):
    """Test publish then subscribe receives message."""
    coordinator = WorkerCoordinator(mock_context)
    received_messages = []

    async def handler(message: dict):
        received_messages.append(message)

    # Subscribe first
    await coordinator._subscribe("test_topic", handler)

    # Then publish
    test_message = {"test": "data"}
    await coordinator._publish("test_topic", test_message)

    assert len(received_messages) == 1
    assert received_messages[0] == test_message


async def test_pubsub_multiple_handlers(mock_context):
    """Test multiple handlers receive the same message."""
    coordinator = WorkerCoordinator(mock_context)
    received_1 = []
    received_2 = []

    async def handler1(message: dict):
        received_1.append(message)

    async def handler2(message: dict):
        received_2.append(message)

    # Subscribe both handlers
    await coordinator._subscribe("test_topic", handler1)
    await coordinator._subscribe("test_topic", handler2)

    # Publish message
    test_message = {"test": "data"}
    await coordinator._publish("test_topic", test_message)

    assert len(received_1) == 1
    assert len(received_2) == 1
    assert received_1[0] == test_message
    assert received_2[0] == test_message


async def test_job_context_methods(mock_context):
    """Test JobContext heartbeat, publish, and subscribe methods work."""
    coordinator = WorkerCoordinator(mock_context)

    # Create a context with the coordinator and job name set
    ctx = coordinator._make_context("test_job")

    # Test heartbeat (should not raise)
    await ctx.heartbeat()

    # Test publish/subscribe
    received = []

    async def handler(message: dict):
        received.append(message)

    await ctx.subscribe("test", handler)
    await ctx.publish("test", {"data": "value"})

    assert len(received) == 1
    assert received[0] == {"data": "value"}


async def test_make_context_sets_job_name(mock_context):
    """Test _make_context properly sets job_name field."""
    coordinator = WorkerCoordinator(mock_context)

    ctx = coordinator._make_context("my_job")

    assert ctx.job_name == "my_job"
    assert ctx._coordinator is coordinator


async def test_graceful_shutdown(mock_context):
    """Test stop() cancels tasks gracefully."""
    coordinator = WorkerCoordinator(mock_context)

    # Create a mock task
    async def long_running_task():
        await asyncio.sleep(10)  # Long task that should be cancelled

    task = asyncio.create_task(long_running_task())
    coordinator._tasks["test"] = task

    # Stop should cancel and wait
    await coordinator.stop()

    assert task.cancelled()
    assert len(coordinator._tasks) == 0