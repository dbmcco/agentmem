# ABOUTME: `am` CLI entry point. Typer app with JSON output by default.
# ABOUTME: Subcommands: ingest, retrieve, facet, graph, digest, context, admin, workers.
"""am — agentmem CLI entry point.

Usage: am [command] [subcommand] [options]
Output: JSON by default; --format text|table for human-readable.

All commands accept --tenant TENANT (defaults to AGENTMEM__TENANCY__DEFAULT_TENANT env var).
All commands use --url to set the service base URL (default: http://localhost:3510).
"""
from __future__ import annotations

import typer

from agentmem.cli.commands.ingest import app as ingest_app
from agentmem.cli.commands.retrieve import app as retrieve_app
from agentmem.cli.commands.facet import app as facet_app
from agentmem.cli.commands.graph import app as graph_app
from agentmem.cli.commands.digest import app as digest_app
from agentmem.cli.commands.context import app as context_app
from agentmem.cli.commands.admin import app as admin_app
from agentmem.cli.commands.workers import app as workers_app

app = typer.Typer(
    name="am",
    help="agentmem CLI — agent-facing memory interface",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

app.add_typer(ingest_app, name="ingest")
app.add_typer(retrieve_app, name="retrieve")
app.add_typer(facet_app, name="facet")
app.add_typer(graph_app, name="graph")
app.add_typer(digest_app, name="digest")
app.add_typer(context_app, name="context")
app.add_typer(admin_app, name="admin")
app.add_typer(workers_app, name="workers")


if __name__ == "__main__":
    app()
