# ABOUTME: CLI layer for agentmem.
# ABOUTME: Typer-based command-line interface for memory operations and admin tasks.

from .commands.main import app, main

__all__ = ["app", "main"]
