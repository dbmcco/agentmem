"""Tests for WebhookEventSourceAdapter."""
import pytest
from agentmem.adapters.events.webhook import WebhookEventSourceAdapter


class TestWebhookEventSourceAdapter:
    """Test WebhookEventSourceAdapter initialization and basic interface."""

    def test_init_with_default_path(self):
        """Test adapter initializes with default webhook path."""
        adapter = WebhookEventSourceAdapter()
        assert adapter._path == '/webhooks/events'
        assert adapter._handler is None

    def test_init_with_custom_path(self):
        """Test adapter initializes with custom webhook path."""
        adapter = WebhookEventSourceAdapter('/custom/webhooks')
        assert adapter._path == '/custom/webhooks'
        assert adapter._handler is None