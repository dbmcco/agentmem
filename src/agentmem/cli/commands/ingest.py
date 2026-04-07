# ABOUTME: CLI ingest subcommands — am ingest evidence.
# ABOUTME: POSTs to service API; outputs JSON to stdout.
"""CLI ingest commands."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import httpx
import typer

app = typer.Typer(help="Ingest data into agentmem", no_args_is_help=True)

# Common options
_URL_OPTION = typer.Option("http://localhost:3510", envvar="AGENTMEM_URL", help="Service URL")
_TENANT_OPTION = typer.Option(..., envvar="AGENTMEM_TENANT", help="Tenant ID")


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
def ingest_evidence(
    tenant: str = _TENANT_OPTION,
    type: str = typer.Option(..., "--type", help="Event type (e.g. conversation.turn)"),
    content: str = typer.Option(..., help="Evidence content text"),
    dedupe_key: str = typer.Option("", "--dedupe-key", help="Deduplication key (auto-generated if empty)"),
    source_event_id: str = typer.Option("", "--source-event-id"),
    metadata: str = typer.Option("{}", help="JSON metadata dict"),
    channel_id: str = typer.Option("", "--channel-id"),
    url: str = _URL_OPTION,
) -> None:
    """Ingest an evidence record.

    Outputs JSON: {"id": int|null, "dedupe_key": str, "deduplicated": bool}
    """
    try:
        metadata_obj = json.loads(metadata)
    except json.JSONDecodeError as e:
        typer.echo(f"Invalid metadata JSON: {e}", err=True)
        raise typer.Exit(1)

    request_body = {
        "tenant_id": tenant,
        "event_type": type,
        "content": content,
    }

    # Add optional fields if provided
    if dedupe_key:
        request_body["dedupe_key"] = dedupe_key
    if source_event_id:
        request_body["source_event_id"] = source_event_id
    if channel_id:
        request_body["channel_id"] = channel_id
    if metadata_obj:
        request_body["metadata"] = metadata_obj

    result = _post(f"{url}/ingest/evidence", request_body)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("facet")
def ingest_facet(
    tenant: str = _TENANT_OPTION,
    key: str = typer.Argument(..., help="Facet key"),
    value: str = typer.Argument(..., help="Facet value"),
    confidence: float = typer.Option(1.0, help="Confidence score"),
    layer: str = typer.Option("runtime", help="Facet layer"),
    url: str = _URL_OPTION,
) -> None:
    """Ingest a facet record."""
    request_body = {
        "tenant_id": tenant,
        "key": key,
        "value": value,
        "confidence": confidence,
        "layer": layer,
    }

    result = _post(f"{url}/ingest/facet", request_body)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("triplet")
def ingest_triplet(
    tenant: str = _TENANT_OPTION,
    subject: str = typer.Argument(..., help="Triplet subject"),
    predicate: str = typer.Argument(..., help="Triplet predicate"),
    object: str = typer.Argument(..., help="Triplet object"),
    confidence: float = typer.Option(1.0, help="Confidence score"),
    source: str = typer.Option(None, help="Source identifier"),
    url: str = _URL_OPTION,
) -> None:
    """Ingest a knowledge graph triplet."""
    request_body = {
        "tenant_id": tenant,
        "subject": subject,
        "predicate": predicate,
        "object": object,
        "confidence": confidence,
    }

    if source:
        request_body["source"] = source

    result = _post(f"{url}/ingest/triplet", request_body)
    typer.echo(json.dumps(result, indent=2, default=str))
