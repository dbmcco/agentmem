# ABOUTME: Unit tests for ActiveContextStore domain service.
# ABOUTME: Tests upsert, get_all with max_age filtering, and delete operations.

import pytest
from datetime import datetime, timedelta
from agentmem.core.models import ContextSection
from agentmem.core.active_context import ActiveContextStore


class MockActiveContextStoreAdapter:
    def __init__(self):
        self._sections: dict[str, ContextSection] = {}

    async def upsert(self, section: ContextSection) -> ContextSection:
        key = f"{section.tenant_id}:{section.section}"
        section.updated_at = datetime.now()
        self._sections[key] = section
        return section

    async def get_all(self, tenant_id: str, max_age_seconds: float | None = None) -> list[ContextSection]:
        sections = [s for s in self._sections.values() if s.tenant_id == tenant_id]

        if max_age_seconds is not None:
            cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
            sections = [s for s in sections if s.updated_at and s.updated_at >= cutoff]

        return sections

    async def delete(self, tenant_id: str, section: str) -> bool:
        key = f"{tenant_id}:{section}"
        if key in self._sections:
            del self._sections[key]
            return True
        return False


class TestActiveContextStore:
    @pytest.mark.asyncio
    async def test_upsert_creates_new_section(self):
        adapter = MockActiveContextStoreAdapter()
        store = ActiveContextStore(adapter)

        result = await store.upsert(ContextSection(tenant_id="tenant1", section="bio", content="Alice is a developer"))

        assert result.tenant_id == "tenant1"
        assert result.section == "bio"
        assert result.content == "Alice is a developer"
        assert result.updated_at is not None

    @pytest.mark.asyncio
    async def test_get_all_filters_by_max_age(self):
        adapter = MockActiveContextStoreAdapter()
        store = ActiveContextStore(adapter)

        # Create sections for different tenants
        await store.upsert(ContextSection(tenant_id="tenant1", section="bio", content="Alice info"))
        await store.upsert(ContextSection(tenant_id="tenant2", section="bio", content="Bob info"))
        await store.upsert(ContextSection(tenant_id="tenant1", section="skills", content="Python, JS"))

        # Get all sections for tenant1
        sections = await store.get_all("tenant1")

        assert len(sections) == 2
        section_names = {s.section for s in sections}
        assert section_names == {"bio", "skills"}

    @pytest.mark.asyncio
    async def test_delete_removes_section(self):
        adapter = MockActiveContextStoreAdapter()
        store = ActiveContextStore(adapter)

        # Create a section
        await store.upsert(ContextSection(tenant_id="tenant1", section="bio", content="Alice info"))

        # Delete it
        result = await store.delete("tenant1", "bio")
        assert result is True

        # Verify it's gone
        sections = await store.get_all("tenant1")
        assert len(sections) == 0

    @pytest.mark.asyncio
    async def test_get_all_filters_stale_sections_by_max_age(self):
        adapter = MockActiveContextStoreAdapter()

        # Create an old section manually in the adapter
        old_section = ContextSection(
            tenant_id="tenant1",
            section="old_bio",
            content="Old info",
            updated_at=datetime.now() - timedelta(seconds=120)  # 2 minutes ago
        )
        key = f"{old_section.tenant_id}:{old_section.section}"
        adapter._sections[key] = old_section

        store = ActiveContextStore(adapter)

        # Add a fresh section
        await store.upsert(ContextSection(tenant_id="tenant1", section="new_bio", content="Fresh info"))

        # Get all sections without age filter (should return both)
        all_sections = await store.get_all("tenant1")
        assert len(all_sections) == 2

        # Get sections with 60 second max age (should only return the fresh one)
        recent_sections = await store.get_all("tenant1", max_age_seconds=60.0)
        assert len(recent_sections) == 1
        assert recent_sections[0].section == "new_bio"