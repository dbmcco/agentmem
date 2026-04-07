# ABOUTME: Core domain layer for agentmem.
# ABOUTME: Exports domain models, protocol interfaces, and the central MemoryService.

from .models import (
    Evidence,
    EvidenceKind,
    Facet,
    RetrievalQuery,
    RetrievalResult,
    VectorEntry,
)
from .protocols import (
    EmbeddingProvider,
    EventBus,
    EvidenceStore,
    FacetStore,
    JobStore,
    VectorStore,
)
from .services import MemoryService

__all__ = [
    "Evidence", "EvidenceKind", "Facet", "RetrievalQuery", "RetrievalResult",
    "VectorEntry", "EmbeddingProvider", "EvidenceStore", "EventBus",
    "FacetStore", "JobStore", "VectorStore", "MemoryService",
]
