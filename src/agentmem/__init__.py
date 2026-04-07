# ABOUTME: Main agentmem package entrypoint.
# ABOUTME: Exports version and key public APIs for the agent memory system.
"""agentmem — a generic, pluggable agent memory system."""

__version__ = "0.1.0"

from agentmem.core.models import Evidence, EvidenceKind, Facet, RetrievalQuery, RetrievalResult
from agentmem.core.services import MemoryService

__all__ = [
    "Evidence", "EvidenceKind", "Facet", "MemoryService",
    "RetrievalQuery", "RetrievalResult",
]
