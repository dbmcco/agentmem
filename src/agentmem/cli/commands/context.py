# ABOUTME: CLI context subcommands — am context set/delete/get.
# ABOUTME: POSTs, DELETEs, and GETs to service API; outputs JSON to stdout.
"""CLI context commands."""
from __future__ import annotations

import json

import httpx
import typer

app = typer.Typer(help="Manage active context sections", no_args_is_help=True)

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


def _delete(url: str) -> dict:
    try:
        r = httpx.delete(url, timeout=30)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        typer.echo(f'Error {e.response.status_code}: {e.response.text}', err=True)
        raise typer.Exit(1)


@app.command("set")
def context_set(
    tenant: str = _TENANT_OPTION,
    section: str = typer.Option(..., help="Context section name"),
    content: str = typer.Option(..., help="Context content"),
    url: str = _URL_OPTION,
) -> None:
    """Set or update a context section.

    Outputs JSON: ContextSection with id, tenant_id, section, content, updated_at.
    """
    request_body = {
        "tenant_id": tenant,
        "section": section,
        "content": content,
    }

    result = _post(f"{url}/context/set", request_body)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("delete")
def context_delete(
    tenant: str = _TENANT_OPTION,
    section: str = typer.Argument(..., help="Context section name to delete"),
    url: str = _URL_OPTION,
) -> None:
    """Delete a context section.

    Outputs JSON: {deleted: bool}
    """
    result = _delete(f"{url}/context/{tenant}/{section}")
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("get")
def context_get(
    tenant: str = _TENANT_OPTION,
    max_age_seconds: float = typer.Option(None, "--max-age-seconds", help="Filter out sections older than this"),
    url: str = _URL_OPTION,
) -> None:
    """Retrieve active context sections. Outputs newline-delimited JSON."""
    params = {
        "tenant_id": tenant,
        "max_age_seconds": max_age_seconds,
    }

    result = _get(f"{url}/retrieve/context", params)

    # Output newline-delimited JSON
    if isinstance(result, list):
        for item in result:
            typer.echo(json.dumps(item, default=str))
    else:
        typer.echo(json.dumps(result, default=str))