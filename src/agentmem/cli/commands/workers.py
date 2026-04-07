# ABOUTME: CLI workers subcommands — am workers status/run.
# ABOUTME: Manage background worker jobs via the service API.
"""CLI workers commands."""
from __future__ import annotations

import json

import httpx
import typer

app = typer.Typer(help="Manage background worker jobs", no_args_is_help=True)

_URL_OPTION = typer.Option("http://localhost:3510", envvar="AGENTMEM_URL")


def _post(url: str, data: dict) -> dict:
    try:
        r = httpx.post(url, json=data, timeout=30)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        typer.echo(f"Error {e.response.status_code}: {e.response.text}", err=True)
        raise typer.Exit(1)


def _get(url: str, params: dict) -> dict:
    try:
        r = httpx.get(
            url, params={k: v for k, v in params.items() if v is not None}, timeout=30
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        typer.echo(f"Error {e.response.status_code}: {e.response.text}", err=True)
        raise typer.Exit(1)


@app.command("status")
def workers_status(url: str = _URL_OPTION) -> None:
    """Show worker job statuses."""
    result = _get(f"{url}/workers/status", {})

    if isinstance(result, list):
        for item in result:
            typer.echo(json.dumps(item, default=str))
    else:
        typer.echo(json.dumps(result, default=str))


@app.command("run")
def workers_run(
    job_name: str = typer.Argument(..., help="Job name to run"),
    url: str = _URL_OPTION,
) -> None:
    """Trigger an on-demand worker job run."""
    result = _post(f"{url}/workers/run/{job_name}", {})
    typer.echo(json.dumps(result, indent=2, default=str))
