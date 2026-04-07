# ABOUTME: CLI graph subcommands — am graph add/query.
"""CLI knowledge graph commands."""
from __future__ import annotations

import json

import httpx
import typer

app = typer.Typer(help="Manage knowledge graph triplets", no_args_is_help=True)

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


@app.command("add")
def graph_add(
    tenant: str = _TENANT_OPTION,
    subject: str = typer.Option(...),
    predicate: str = typer.Option(...),
    object: str = typer.Option(...),
    confidence: float = typer.Option(1.0),
    url: str = _URL_OPTION,
) -> None:
    """Add a knowledge graph triplet."""
    request_body = {
        "tenant_id": tenant,
        "subject": subject,
        "predicate": predicate,
        "object": object,
        "confidence": confidence,
    }

    result = _post(f"{url}/ingest/triplet", request_body)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("query")
def graph_query(
    tenant: str = _TENANT_OPTION,
    subject: str = typer.Option(None),
    predicate: str = typer.Option(None),
    object: str = typer.Option(None),
    url: str = _URL_OPTION,
) -> None:
    """Query knowledge graph triplets by subject, predicate, or object."""
    params = {
        "tenant_id": tenant,
        "subject": subject,
        "predicate": predicate,
        "object": object,
    }

    result = _get(f"{url}/retrieve/graph", params)

    # Output newline-delimited JSON
    if isinstance(result, list):
        for item in result:
            typer.echo(json.dumps(item, default=str))
    else:
        typer.echo(json.dumps(result, default=str))
