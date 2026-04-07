# ABOUTME: FastAPI service layer for agentmem HTTP API.
# ABOUTME: Main service entrypoint and configuration for memory operations.
"""FastAPI service layer for agentmem."""

from __future__ import annotations

from fastapi import FastAPI

from agentmem.core.services import MemoryService
from agentmem.service.api.routes import router, set_service


def create_app(service: MemoryService) -> FastAPI:
    """Create a FastAPI application with the given MemoryService."""
    app = FastAPI(title="agentmem", version="0.1.0")
    set_service(service)
    app.include_router(router)
    return app
