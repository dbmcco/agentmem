# ABOUTME: Event bus adapter implementations.
# ABOUTME: Provides LocalEventBus for in-process pub/sub event distribution.

from .local import LocalEventBus

__all__ = ["LocalEventBus"]
