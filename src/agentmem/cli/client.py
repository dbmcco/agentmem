# ABOUTME: Thin HTTP client wrapping the agentmem service API.
# ABOUTME: Used by CLI commands; base URL from AGENTMEM_URL env var or --url flag.
"""AgentMemClient — thin HTTP wrapper for CLI commands."""
from __future__ import annotations

import json
import os

import httpx


class AgentMemClient:
    """Thin HTTP client for the agentmem service API."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base = (
            base_url
            or os.environ.get("AGENTMEM_URL", "http://localhost:3510")
        ).rstrip("/")

    def get(self, path: str, **params: object) -> dict | list:
        with httpx.Client(timeout=30) as c:
            r = c.get(
                f"{self._base}{path}",
                params={k: v for k, v in params.items() if v is not None},
            )
            r.raise_for_status()
            return r.json()

    def post(self, path: str, body: dict) -> dict | list:
        with httpx.Client(timeout=30) as c:
            r = c.post(f"{self._base}{path}", json=body)
            r.raise_for_status()
            return r.json()


def output_json(data: object) -> None:
    """Print data as indented JSON to stdout."""
    print(json.dumps(data, indent=2, default=str))


def output_text(data: object) -> None:
    """Pretty-print data for human consumption."""
    if isinstance(data, dict):
        for k, v in data.items():
            print(f"{k}: {v}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for k, v in item.items():
                    print(f"  {k}: {v}")
                print()
            else:
                print(f"  {item}")
    else:
        print(data)
