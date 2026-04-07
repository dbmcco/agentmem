# ABOUTME: Trigger type dataclasses for the worker coordinator.
# ABOUTME: Exactly four types as spec'd: CronTrigger, ContinuousTrigger, EventTrigger, OnDemandTrigger.
"""Worker trigger types.

Parse from config strings via WorkerCoordinator.parse_trigger():
  "cron:0 2 * * *"            → CronTrigger("0 2 * * *")
  "continuous:pg_listen"      → ContinuousTrigger(source="pg_listen")
  "event:pg_listen:gcal.*"    → EventTrigger(source="pg_listen", event_type_pattern="gcal.*")
  "on_demand"                 → OnDemandTrigger()
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CronTrigger:
    schedule: str  # standard cron expression, e.g. "0 2 * * *"


@dataclass
class ContinuousTrigger:
    source: str  # event source adapter name


@dataclass
class EventTrigger:
    source: str
    event_type_pattern: str  # glob, e.g. "gcal.*"


@dataclass
class OnDemandTrigger:
    pass  # only runs when explicitly invoked via API/CLI


# Union type for type annotations
AnyTrigger = CronTrigger | ContinuousTrigger | EventTrigger | OnDemandTrigger


def parse_trigger(trigger_string: str) -> AnyTrigger:
    """Parse a trigger config string into a Trigger dataclass.

    Raises ValueError for unrecognised formats.
    """
    if trigger_string == "on_demand":
        return OnDemandTrigger()
    if trigger_string.startswith("cron:"):
        schedule = trigger_string[len("cron:"):]
        return CronTrigger(schedule=schedule)
    if trigger_string.startswith("continuous:"):
        source = trigger_string[len("continuous:"):]
        return ContinuousTrigger(source=source)
    if trigger_string.startswith("event:"):
        parts = trigger_string[len("event:"):].split(":", 1)
        if len(parts) != 2:
            raise ValueError(
                f"event trigger must be 'event:<source>:<pattern>', got: {trigger_string!r}"
            )
        return EventTrigger(source=parts[0], event_type_pattern=parts[1])
    raise ValueError(f"unrecognised trigger string: {trigger_string!r}")
