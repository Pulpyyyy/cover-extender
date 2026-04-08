"""Tests for __init__.py: async_setup, async_setup_entry, async_unload_entry."""
from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cover_extender.const import (
    DOMAIN,
    DATA_COVER_PROFILES,
    DATA_MODES,
    DATA_SHOW_ENTITIES,
    DATA_SOLAR_GAIN,
    DATA_FACADES,
    DATA_MEMORY,
    CONF_SOURCE,
    SERVICE_APPLY_MODE,
    SERVICE_RELOAD,
    SERVICE_GET_MODE_POSITION,
    SERVICE_COMPUTE_SHADE_POSITION,
    SERVICE_SET_COVER_POSITION,
    SERVICE_OPEN_COVER,
    SERVICE_CLOSE_COVER,
    SERVICE_APPLY_MEMORY,
)
from custom_components.cover_extender.coordinator import CoverExtenderCoordinator


def test_init_import():
    import custom_components.cover_extender
    assert custom_components.cover_extender is not None


# ════════════════════════════════════════════════════════════════════════════
# async_setup
# ════════════════════════════════════════════════════════════════════════════

class TestAsyncSetup:

    async def test_with_domain_in_config_creates_task(self, hass):
        from custom_components.cover_extender import async_setup
        with patch.object(hass.config_entries.flow, "async_init",
                          new_callable=AsyncMock) as mock_init:
            result = await async_setup(hass, {DOMAIN: {CONF_SOURCE: "covers.yaml"}})
        assert result is True
        await hass.async_block_till_done()
        mock_init.assert_called_once()

    async def test_without_domain_in_config_returns_true(self, hass):
        from custom_components.cover_extender import async_setup
        result = await async_setup(hass, {})
        assert result is True


# ════════════════════════════════════════════════════════════════════════════
# async_setup_entry
# ════════════════════════════════════════════════════════════════════════════

class TestAsyncSetupEntry:

    @pytest.fixture
    def entry_no_source(self, hass):
        entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, unique_id="no_src")
        entry.add_to_hass(hass)
        return entry

    @pytest.fixture
    def entry_with_source(self, hass, tmp_path):
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][DATA_COVER_PROFILES] = {"cover.test": {}}
        hass.data[DOMAIN][DATA_SHOW_ENTITIES] = {"sun_facing": False, "auto_shade": False, "solar_gain": False}

        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump({"cover.test": {}}), encoding="utf-8")
        entry = MockConfigEntry(
            domain=DOMAIN, data={CONF_SOURCE: str(f)}, options={}, unique_id="with_src"
        )
        entry.add_to_hass(hass)
        return entry

    async def test_no_source_returns_false(self, hass, entry_no_source):
        from custom_components.cover_extender import async_setup_entry
        result = await async_setup_entry(hass, entry_no_source)
        assert result is False

    async def test_success_returns_true(self, hass, entry_with_source):
        from custom_components.cover_extender import async_setup_entry
        with patch.object(CoverExtenderCoordinator, "async_start", new_callable=AsyncMock):
            with patch.object(hass.config_entries, "async_forward_entry_setups",
                              new_callable=AsyncMock, return_value=True):
                result = await async_setup_entry(hass, entry_with_source)
        assert result is True

    async def test_coordinator_stored_in_hass_data(self, hass, entry_with_source):
        from custom_components.cover_extender import async_setup_entry
        with patch.object(CoverExtenderCoordinator, "async_start", new_callable=AsyncMock):
            with patch.object(hass.config_entries, "async_forward_entry_setups",
                              new_callable=AsyncMock, return_value=True):
                await async_setup_entry(hass, entry_with_source)
        assert "coordinator" in hass.data[DOMAIN]
        assert isinstance(hass.data[DOMAIN]["coordinator"], CoverExtenderCoordinator)

    async def test_services_registered(self, hass, entry_with_source):
        from custom_components.cover_extender import async_setup_entry
        with patch.object(CoverExtenderCoordinator, "async_start", new_callable=AsyncMock):
            with patch.object(hass.config_entries, "async_forward_entry_setups",
                              new_callable=AsyncMock, return_value=True):
                await async_setup_entry(hass, entry_with_source)

        for svc in (SERVICE_APPLY_MODE, SERVICE_RELOAD, SERVICE_GET_MODE_POSITION,
                    SERVICE_COMPUTE_SHADE_POSITION, SERVICE_SET_COVER_POSITION,
                    SERVICE_OPEN_COVER, SERVICE_CLOSE_COVER, SERVICE_APPLY_MEMORY):
            assert hass.services.has_service(DOMAIN, svc), f"Service {svc} not registered"


# ════════════════════════════════════════════════════════════════════════════
# async_unload_entry
# ════════════════════════════════════════════════════════════════════════════

class TestAsyncUnloadEntry:

    @pytest.fixture
    def entry_with_source(self, hass, tmp_path):
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][DATA_COVER_PROFILES] = {"cover.test": {}}
        hass.data[DOMAIN][DATA_SHOW_ENTITIES] = {"sun_facing": False, "auto_shade": False, "solar_gain": False}

        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump({"cover.test": {}}), encoding="utf-8")
        entry = MockConfigEntry(
            domain=DOMAIN, data={CONF_SOURCE: str(f)}, options={}, unique_id="unload_test"
        )
        entry.add_to_hass(hass)
        return entry

    async def test_unload_stops_coordinator(self, hass, entry_with_source):
        from custom_components.cover_extender import async_setup_entry, async_unload_entry

        with patch.object(CoverExtenderCoordinator, "async_start", new_callable=AsyncMock):
            with patch.object(hass.config_entries, "async_forward_entry_setups",
                              new_callable=AsyncMock, return_value=True):
                await async_setup_entry(hass, entry_with_source)

        coordinator = hass.data[DOMAIN]["coordinator"]
        with patch.object(coordinator, "async_stop", new_callable=AsyncMock) as mock_stop:
            with patch.object(hass.config_entries, "async_unload_platforms",
                              new_callable=AsyncMock, return_value=True):
                result = await async_unload_entry(hass, entry_with_source)

        assert result is True
        mock_stop.assert_called_once()

    async def test_unload_removes_services(self, hass, entry_with_source):
        from custom_components.cover_extender import async_setup_entry, async_unload_entry

        with patch.object(CoverExtenderCoordinator, "async_start", new_callable=AsyncMock):
            with patch.object(hass.config_entries, "async_forward_entry_setups",
                              new_callable=AsyncMock, return_value=True):
                await async_setup_entry(hass, entry_with_source)

        coordinator = hass.data[DOMAIN]["coordinator"]
        with patch.object(coordinator, "async_stop", new_callable=AsyncMock):
            with patch.object(hass.config_entries, "async_unload_platforms",
                              new_callable=AsyncMock, return_value=True):
                await async_unload_entry(hass, entry_with_source)

        for svc in (SERVICE_APPLY_MODE, SERVICE_RELOAD, SERVICE_GET_MODE_POSITION,
                    SERVICE_COMPUTE_SHADE_POSITION, SERVICE_SET_COVER_POSITION,
                    SERVICE_OPEN_COVER, SERVICE_CLOSE_COVER, SERVICE_APPLY_MEMORY):
            assert not hass.services.has_service(DOMAIN, svc), f"Service {svc} still registered"

    async def test_unload_platforms_failure_returns_false(self, hass, entry_with_source):
        from custom_components.cover_extender import async_setup_entry, async_unload_entry

        with patch.object(CoverExtenderCoordinator, "async_start", new_callable=AsyncMock):
            with patch.object(hass.config_entries, "async_forward_entry_setups",
                              new_callable=AsyncMock, return_value=True):
                await async_setup_entry(hass, entry_with_source)

        coordinator = hass.data[DOMAIN]["coordinator"]
        with patch.object(coordinator, "async_stop", new_callable=AsyncMock):
            with patch.object(hass.config_entries, "async_unload_platforms",
                              new_callable=AsyncMock, return_value=False):
                result = await async_unload_entry(hass, entry_with_source)

        assert result is False

    async def test_unload_without_coordinator_is_safe(self, hass, entry_with_source):
        from custom_components.cover_extender import async_setup_entry, async_unload_entry

        with patch.object(CoverExtenderCoordinator, "async_start", new_callable=AsyncMock):
            with patch.object(hass.config_entries, "async_forward_entry_setups",
                              new_callable=AsyncMock, return_value=True):
                await async_setup_entry(hass, entry_with_source)

        # Remove coordinator manually
        hass.data[DOMAIN].pop("coordinator", None)

        with patch.object(hass.config_entries, "async_unload_platforms",
                          new_callable=AsyncMock, return_value=True):
            result = await async_unload_entry(hass, entry_with_source)

        assert result is True
