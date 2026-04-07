# ABOUTME: CLI commands for the `am` command-line tool.
# ABOUTME: Typer-based ingest and retrieve commands for memory operations.
"""CLI commands for agentmem — the `am` command."""

from __future__ import annotations

import asyncio
import json

import typer
from rich.console import Console
from rich.table import Table

from agentmem.adapters.embeddings import HashEmbeddingProvider
from agentmem.adapters.events import LocalEventBus
from agentmem.adapters.storage import MemoryEvidenceStore, MemoryVectorStore
from agentmem.core.models import EvidenceKind, RetrievalQuery
from agentmem.core.services import MemoryService

app = typer.Typer(name="am", help="agentmem CLI — agent memory management")
console = Console()

# Shared in-process state for CLI session
_service: MemoryService | None = None


def _get_service() -> MemoryService:
    global _service
    if _service is None:
        _service = MemoryService(
            evidence_store=MemoryEvidenceStore(),
            vector_store=MemoryVectorStore(),
            embedding_provider=HashEmbeddingProvider(),
            event_bus=LocalEventBus(),
        )
    return _service


@app.command()
def ingest(
    content: str = typer.Argument(..., help="Content to ingest"),
    tenant: str = typer.Option("default", "--tenant", "-t", help="Tenant ID"),
    kind: str = typer.Option("observation", "--kind", "-k", help="Evidence kind"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Ingest evidence into memory."""
    svc = _get_service()
    ev_kind = EvidenceKind(kind)
    evidence = asyncio.run(svc.ingest(tenant, content, ev_kind))
    if output_json:
        typer.echo(
            json.dumps(
                {
                    "id": str(evidence.id),
                    "tenant_id": evidence.tenant_id,
                    "content": evidence.content,
                    "kind": evidence.kind.value,
                    "created_at": evidence.created_at.isoformat(),
                }
            )
        )
    else:
        console.print(f"[green]Ingested[/green] {evidence.id} ({evidence.kind.value})")


@app.command()
def retrieve(
    query: str = typer.Argument(..., help="Search query text"),
    tenant: str = typer.Option("default", "--tenant", "-t", help="Tenant ID"),
    top_k: int = typer.Option(10, "--top-k", "-n", help="Max results"),
    kind: str | None = typer.Option(None, "--kind", "-k", help="Filter by kind"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Retrieve evidence by semantic similarity."""
    svc = _get_service()
    kind_filter = EvidenceKind(kind) if kind else None
    rq = RetrievalQuery(
        tenant_id=tenant, text=query, top_k=top_k, kind_filter=kind_filter
    )
    results = asyncio.run(svc.retrieve(rq))
    if output_json:
        typer.echo(
            json.dumps(
                [
                    {
                        "id": str(r.evidence.id),
                        "content": r.evidence.content,
                        "kind": r.evidence.kind.value,
                        "score": r.score,
                    }
                    for r in results
                ]
            )
        )
    else:
        table = Table(title="Results")
        table.add_column("Score", width=8)
        table.add_column("Kind", width=12)
        table.add_column("Content")
        for r in results:
            table.add_row(f"{r.score:.4f}", r.evidence.kind.value, r.evidence.content)
        console.print(table)


def main() -> None:
    app()
