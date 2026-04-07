# ABOUTME: CLI retrieve subcommands — am retrieve evidence, am retrieve semantic.
# ABOUTME: GETs from service API; outputs newline-delimited JSON to stdout.
"""CLI retrieval commands."""
from __future__ import annotations

import json

import httpx
import typer

app = typer.Typer(help="Retrieve data from agentmem", no_args_is_help=True)

_URL_OPTION = typer.Option("http://localhost:3510", envvar="AGENTMEM_URL")
_TENANT_OPTION = typer.Option(..., envvar="AGENTMEM_TENANT")


def _post(url: str, data: dict) -> dict:
    try:
        r = httpx.post(url, json=data, timeout=30)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        typer.echo(f'Error {e.response.status_code}: {e.response.text}', err=True)
        raise typer.Exit(1)


def _get(url: str, params: dict) -> dict:
    try:
        r = httpx.get(url, params={k: v for k, v in params.items() if v is not None}, timeout=30)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        typer.echo(f'Error {e.response.status_code}: {e.response.text}', err=True)
        raise typer.Exit(1)


@app.command("evidence")
def retrieve_evidence(
    tenant: str = _TENANT_OPTION,
    type: str = typer.Option(None, "--type"),
    since: str = typer.Option(None, help="ISO date filter"),
    limit: int = typer.Option(50),
    url: str = _URL_OPTION,
) -> None:
    """Retrieve evidence records. Outputs newline-delimited JSON."""
    params = {
        "tenant_id": tenant,
        "event_type": type,
        "since": since,
        "limit": limit,
    }

    result = _get(f"{url}/retrieve/evidence", params)

    # Output newline-delimited JSON
    if isinstance(result, list):
        for item in result:
            typer.echo(json.dumps(item, default=str))
    else:
        typer.echo(json.dumps(result, default=str))


@app.command("semantic")
def retrieve_semantic(
    tenant: str = _TENANT_OPTION,
    query: str = typer.Option(..., "--q", help="Semantic search query"),
    source_table: str = typer.Option(None, "--source-table", help="evidence|facets"),
    limit: int = typer.Option(10),
    url: str = _URL_OPTION,
) -> None:
    """Semantic similarity search. Outputs newline-delimited JSON results."""
    params = {
        "tenant_id": tenant,
        "q": query,
        "source_table": source_table,
        "limit": limit,
    }

    result = _get(f"{url}/retrieve/semantic", params)

    # Output newline-delimited JSON
    if isinstance(result, list):
        for item in result:
            typer.echo(json.dumps(item, default=str))
    else:
        typer.echo(json.dumps(result, default=str))


@app.command("context")
def retrieve_context(
    tenant: str = _TENANT_OPTION,
    max_age: float = typer.Option(None, "--max-age-seconds"),
    url: str = _URL_OPTION,
) -> None:
    """Retrieve active context sections. Outputs newline-delimited JSON."""
    params = {
        "tenant_id": tenant,
        "max_age_seconds": max_age,
    }

    result = _get(f"{url}/retrieve/context", params)

    # Output newline-delimited JSON
    if isinstance(result, list):
        for item in result:
            typer.echo(json.dumps(item, default=str))
    else:
        typer.echo(json.dumps(result, default=str))
