# ABOUTME: CLI facet subcommands — am facet get/set/list/delete.
"""CLI facet commands."""
from __future__ import annotations

import json

import httpx
import typer

app = typer.Typer(help="Manage facets (key-value structured memory)", no_args_is_help=True)

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


def _delete(url: str, params: dict = None) -> dict:
    try:
        r = httpx.delete(url, params={k: v for k, v in (params or {}).items() if v is not None}, timeout=30)
        r.raise_for_status()
        return r.json() if r.text else {}
    except httpx.HTTPStatusError as e:
        typer.echo(f'Error {e.response.status_code}: {e.response.text}', err=True)
        raise typer.Exit(1)


@app.command("get")
def facet_get(tenant: str = _TENANT_OPTION, key: str = typer.Option(...), url: str = _URL_OPTION) -> None:
    """Get a facet by key. Outputs JSON or null if not found."""
    params = {
        "tenant_id": tenant,
        "prefix": key,
    }

    result = _get(f"{url}/retrieve/facets", params)

    # Find the first match with exact key
    if isinstance(result, list):
        for facet in result:
            if facet.get("key") == key:
                typer.echo(json.dumps(facet, indent=2, default=str))
                return
        typer.echo("null")
    else:
        typer.echo(json.dumps(result, indent=2, default=str))


@app.command("set")
def facet_set(
    tenant: str = _TENANT_OPTION,
    key: str = typer.Option(...),
    value: str = typer.Option(...),
    confidence: float = typer.Option(1.0),
    layer: str = typer.Option("searchable"),
    url: str = _URL_OPTION,
) -> None:
    """Set (upsert) a facet. Outputs stored facet JSON."""
    request_body = {
        "tenant_id": tenant,
        "key": key,
        "value": value,
        "confidence": confidence,
        "layer": layer,
    }

    result = _post(f"{url}/ingest/facet", request_body)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("list")
def facet_list(
    tenant: str = _TENANT_OPTION,
    prefix: str = typer.Option(None),
    layer: str = typer.Option(None),
    url: str = _URL_OPTION,
) -> None:
    """List facets. Outputs newline-delimited JSON."""
    params = {
        "tenant_id": tenant,
        "prefix": prefix,
        "layer": layer,
    }

    result = _get(f"{url}/retrieve/facets", params)

    # Output newline-delimited JSON
    if isinstance(result, list):
        for item in result:
            typer.echo(json.dumps(item, default=str))
    else:
        typer.echo(json.dumps(result, default=str))


@app.command("delete")
def facet_delete(tenant: str = _TENANT_OPTION, key: str = typer.Option(...), url: str = _URL_OPTION) -> None:
    """Delete a facet by key."""
    params = {
        "tenant_id": tenant,
    }

    result = _delete(f"{url}/facets/{tenant}/{key}", params)
    typer.echo(json.dumps(result, indent=2, default=str))
