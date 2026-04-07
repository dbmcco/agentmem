# ABOUTME: CLI digest subcommands — am digest generate/list.
"""CLI digest commands."""
from __future__ import annotations

import json

import httpx
import typer

app = typer.Typer(help="Manage memory digests", no_args_is_help=True)

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


@app.command("generate")
def digest_generate(
    tenant: str = _TENANT_OPTION,
    type: str = typer.Option(..., "--type", help="daily|weekly|monthly"),
    date: str = typer.Option(..., help="ISO date (YYYY-MM-DD)"),
    url: str = _URL_OPTION,
) -> None:
    """Generate a digest for the given period."""
    request_body = {
        "tenant_id": tenant,
        "digest_type": type,
        "date": date,
    }

    result = _post(f"{url}/admin/digest/generate", request_body)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("list")
def digest_list(
    tenant: str = _TENANT_OPTION,
    type: str = typer.Option(None, "--type"),
    limit: int = typer.Option(50),
    url: str = _URL_OPTION,
) -> None:
    """List stored digests."""
    params = {
        "tenant_id": tenant,
        "type": type,
        "limit": limit,
    }

    result = _get(f"{url}/retrieve/digests", params)

    # Output newline-delimited JSON
    if isinstance(result, list):
        for item in result:
            typer.echo(json.dumps(item, default=str))
    else:
        typer.echo(json.dumps(result, default=str))
