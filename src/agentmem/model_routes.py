# ABOUTME: Resolves semantic model route IDs from the shared Paia model route registry.
# ABOUTME: Reads cognition-presets.toml; no model literals live in agentmem source.
"""Lightweight resolver for the central Paia model route registry.

Mirrors the contract used by other consumers (e.g. ``lfw-ai-graph-crm``):
the registry TOML file is the single source of truth for model identifiers,
and runtime code references routes by their semantic ID.
"""
from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

OLLAMA_EMBEDDING_ROUTE_ID = "agentmem.ollama_embedding"

_REGISTRY_ENV_VAR = "PAIA_MODEL_ROUTE_REGISTRY_PATH"
_RELATIVE_REGISTRY_CANDIDATES: tuple[str, ...] = (
    "../paia-agent-runtime/config/cognition-presets.toml",
    "../../paia-agent-runtime/config/cognition-presets.toml",
    "../../../paia-agent-runtime/config/cognition-presets.toml",
)


class ModelRoute(NamedTuple):
    id: str
    owner: str
    surface: str
    provider: str
    model: str


class ModelRouteError(RuntimeError):
    """Raised when the registry cannot be located or a route is missing."""


def model_for_route(route_id: str) -> str:
    """Return the registered model identifier for ``route_id``."""
    return resolve_route(route_id).model


def resolve_route(route_id: str) -> ModelRoute:
    """Look up a model route by ID, raising ``ModelRouteError`` if absent."""
    normalized = route_id.strip().lower()
    if not normalized:
        raise ModelRouteError("route_id must not be blank")
    routes = _load_routes()
    try:
        return routes[normalized]
    except KeyError as exc:
        raise ModelRouteError(f"Unknown model route: {route_id!r}") from exc


def clear_route_cache() -> None:
    """Clear the cached registry parse (test helper)."""
    _load_routes.cache_clear()


@lru_cache(maxsize=1)
def _load_routes() -> dict[str, ModelRoute]:
    path = _resolve_registry_path()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ModelRouteError(f"Failed to parse model route registry {path}: {exc}") from exc

    raw_routes = raw.get("model_routes")
    if not isinstance(raw_routes, dict):
        raise ModelRouteError(f"Registry {path} does not define model_routes")

    routes: dict[str, ModelRoute] = {}
    for raw_id, body in raw_routes.items():
        if not isinstance(body, dict):
            continue
        normalized_id = str(raw_id).strip().lower()
        try:
            routes[normalized_id] = ModelRoute(
                id=normalized_id,
                owner=str(body["owner"]).strip(),
                surface=str(body["surface"]).strip().lower(),
                provider=str(body["provider"]).strip().lower(),
                model=str(body["model"]).strip(),
            )
        except KeyError as exc:
            raise ModelRouteError(
                f"Registry {path} route {normalized_id!r} missing field {exc.args[0]!r}"
            ) from exc
    return routes


def _resolve_registry_path() -> Path:
    configured = os.environ.get(_REGISTRY_ENV_VAR, "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return candidate
        raise ModelRouteError(
            f"{_REGISTRY_ENV_VAR}={configured!r} does not point at a readable file"
        )

    cwd = Path.cwd()
    package_root = Path(__file__).resolve().parents[2]
    search_bases = [cwd, package_root]
    for base in search_bases:
        for relative in _RELATIVE_REGISTRY_CANDIDATES:
            candidate = (base / relative).resolve()
            if candidate.is_file():
                return candidate

    raise ModelRouteError(
        "Unable to locate the Paia model route registry "
        f"(set {_REGISTRY_ENV_VAR} or place cognition-presets.toml in a sibling "
        "paia-agent-runtime checkout)"
    )


__all__ = [
    "ModelRoute",
    "ModelRouteError",
    "OLLAMA_EMBEDDING_ROUTE_ID",
    "clear_route_cache",
    "model_for_route",
    "resolve_route",
]
