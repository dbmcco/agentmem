# ABOUTME: Tests for EventRouter pattern matching and content formatting.
# ABOUTME: Verifies glob patterns, formatter dispatch, and section routing.
"""Tests for EventRouter."""
import pytest
from datetime import datetime

from agentmem.core.router import EventRouter
from agentmem.core.models import EventRecord


def test_register_and_format():
    """Test register 'gmail.*' formatter; format event with type 'gmail.inbox' returns formatted string."""
    router = EventRouter()

    def gmail_formatter(event: EventRecord) -> str:
        return f"Email: {event.payload['subject']}"

    router.register("gmail.*", gmail_formatter)

    event = EventRecord(
        event_type="gmail.inbox",
        payload={"subject": "Test Email"},
        occurred_at=datetime.now(),
        dedupe_key="test-key"
    )

    result = router.format(event)
    assert result == "Email: Test Email"


def test_first_match_wins():
    """Test register 'gmail.*' and '*'; gmail event hits first route."""
    router = EventRouter()

    def gmail_formatter(event: EventRecord) -> str:
        return "Gmail formatter"

    def fallback_formatter(event: EventRecord) -> str:
        return "Fallback formatter"

    router.register("gmail.*", gmail_formatter)
    router.register("*", fallback_formatter)

    event = EventRecord(
        event_type="gmail.inbox",
        payload={},
        occurred_at=datetime.now(),
        dedupe_key="test-key"
    )

    result = router.format(event)
    assert result == "Gmail formatter"


def test_no_match_raises_key_error():
    """Test unregistered event type raises KeyError."""
    router = EventRouter()

    def gmail_formatter(event: EventRecord) -> str:
        return "Gmail formatter"

    router.register("gmail.*", gmail_formatter)

    event = EventRecord(
        event_type="slack.message",
        payload={},
        occurred_at=datetime.now(),
        dedupe_key="test-key"
    )

    with pytest.raises(KeyError, match=r"No route matches event_type.*slack\.message"):
        router.format(event)


def test_section_for_returns_section():
    """Test registered route with section returns it."""
    router = EventRouter()

    def gmail_formatter(event: EventRecord) -> str:
        return "Gmail formatter"

    router.register("gmail.*", gmail_formatter, section="email")

    event = EventRecord(
        event_type="gmail.inbox",
        payload={},
        occurred_at=datetime.now(),
        dedupe_key="test-key"
    )

    result = router.section_for(event)
    assert result == "email"


def test_section_for_returns_none():
    """Test registered route without section returns None."""
    router = EventRouter()

    def gmail_formatter(event: EventRecord) -> str:
        return "Gmail formatter"

    router.register("gmail.*", gmail_formatter)  # no section specified

    event = EventRecord(
        event_type="gmail.inbox",
        payload={},
        occurred_at=datetime.now(),
        dedupe_key="test-key"
    )

    result = router.section_for(event)
    assert result is None


def test_wildcard_fallback():
    """Test '*' pattern matches any event_type."""
    router = EventRouter()

    def fallback_formatter(event: EventRecord) -> str:
        return f"Fallback: {event.event_type}"

    router.register("*", fallback_formatter)

    # Test various event types
    test_cases = ["gmail.inbox", "slack.message", "gcal.event", "some.random.type"]

    for event_type in test_cases:
        event = EventRecord(
            event_type=event_type,
            payload={},
            occurred_at=datetime.now(),
            dedupe_key="test-key"
        )

        result = router.format(event)
        assert result == f"Fallback: {event_type}"