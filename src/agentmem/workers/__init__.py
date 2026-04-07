# ABOUTME: Background worker layer for agentmem.
# ABOUTME: Exports the WorkerCoordinator for managing async jobs like embedding and retention.

from .coordinator import WorkerCoordinator

__all__ = ["WorkerCoordinator"]
