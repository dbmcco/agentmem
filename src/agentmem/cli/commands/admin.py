# ABOUTME: CLI admin subcommands — am admin reindex/retention/stats.
"""CLI admin and workers commands."""
from __future__ import annotations

import json

import httpx
import typer

app = typer.Typer(help="Admin and worker management", no_args_is_help=True)

_URL_OPTION = typer.Option("http://localhost:3510", envvar="AGENTMEM_URL")
_TENANT_OPTION = typer.Option(None, envvar="AGENTMEM_TENANT")


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


@app.command("reindex")
def admin_reindex(
    tenant: str = _TENANT_OPTION,
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = _URL_OPTION,
) -> None:
    """Trigger embedding reindex."""
    request_body = {
        "dry_run": dry_run,
    }

    if tenant:
        request_body["tenant_id"] = tenant

    result = _post(f"{url}/admin/reindex", request_body)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("retention")
def admin_retention(
    tenant: str = _TENANT_OPTION,
    evidence_days: int = typer.Option(180, "--evidence-days"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = _URL_OPTION,
) -> None:
    """Trigger retention pruning."""
    request_body = {
        "evidence_days": evidence_days,
        "dry_run": dry_run,
    }

    if tenant:
        request_body["tenant_id"] = tenant

    result = _post(f"{url}/admin/retention", request_body)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("stats")
def admin_stats(tenant: str = _TENANT_OPTION, url: str = _URL_OPTION) -> None:
    """Show storage statistics for tenant."""
    params = {
        "tenant_id": tenant,
    }

    result = _get(f"{url}/admin/stats", params)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("workers-status")
def workers_status(url: str = _URL_OPTION) -> None:
    """Show worker job statuses."""
    result = _get(f"{url}/workers/status", {})
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("workers-run")
def workers_run(
    job_name: str = typer.Argument(..., help="Job name to run"),
    url: str = _URL_OPTION,
) -> None:
    """Trigger an on-demand worker job run."""
    result = _post(f"{url}/workers/run/{job_name}", {})
    typer.echo(json.dumps(result, indent=2, default=str))
