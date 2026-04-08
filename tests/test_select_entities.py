"""Tests for select entity classes."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.cover_extender.select import CoverModeSelect, CoverModesGlobalSelect
from custom_components.cover_extender.const import DOMAIN, DATA_COVER_PROFILES, DATA_MODES


_MODES_LIST = {
    "Day":   {"icon": "mdi:sun",  "color": "orange", "lock": False, "auto_shade": False, "solar_gain": False, "hidden": False},
    "Night": {"icon": "mdi:moon", "color": "blue",   "lock": True,  "auto_shade": False, "solar_gain": False, "hidden": False},
    "Hidden":{"icon": "mdi:eye",  "color": "grey",   "lock": False, "auto_shade": False, "solar_gain": False, "hidden": True},
}

_COVER_CFG = {"modes": {"Day": 40, "Night": 0}}


@pytest.fixture
def setup_hass(hass):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_MODES] = dict(_MODES_LIST)
    hass.data[DOMAIN][DATA_COVER_PROFILES] = {
        "cover.test": dict(_COVER_CFG)
    }
    return hass


# ════════════════════════════════════════════════════════════════════════════
# CoverModeSelect
# ════════════════════════════════════════════════════════════════════════════

class TestCoverModeSelect:

    def test_options_from_modes(self, setup_hass):
        sel = CoverModeSelect("cover.test", _COVER_CFG, _MODES_LIST)
        assert set(sel._attr_options) == {"Day", "Night"}

    def test_initial_option_is_first(self, setup_hass):
        sel = CoverModeSelect("cover.test", _COVER_CFG, _MODES_LIST)
        assert sel._attr_current_option == "Day"

    def test_icon_uses_modes_list(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _COVER_CFG, _MODES_LIST)
        sel.hass = hass
        sel._attr_current_option = "Day"
        assert sel.icon == "mdi:sun"

    def test_icon_unknown_option_fallback(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _COVER_CFG, _MODES_LIST)
        sel.hass = hass
        sel._attr_current_option = "Unknown"
        assert sel.icon == "mdi:help-circle-outline"

    def test_extra_state_attributes_structure(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _COVER_CFG, _MODES_LIST)
        sel.hass = hass
        sel._attr_current_option = "Day"
        attrs = sel.extra_state_attributes
        assert attrs["color"] == "orange"
        assert "modes_list" in attrs
        assert "Day" in attrs["modes_list"]
        assert "Night" in attrs["modes_list"]

    def test_handle_reload_updates_options(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _COVER_CFG, _MODES_LIST)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        sel._attr_current_option = "Day"

        # Simulate reload: add a new mode
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["modes"] = {"Day": 40, "Night": 0, "Auto": None}
        sel._handle_reload()
        assert "Auto" in sel._attr_options

    def test_handle_reload_same_options_noop(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _COVER_CFG, _MODES_LIST)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        sel._attr_current_option = "Day"
        original_options = list(sel._attr_options)
        sel._handle_reload()
        assert sel._attr_options == original_options

    def test_handle_reload_resets_current_if_removed(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _COVER_CFG, _MODES_LIST)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        sel._attr_current_option = "Night"

        # Remove "Night" from profile
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["modes"] = {"Day": 40}
        sel._handle_reload()
        assert sel._attr_current_option == "Day"

    async def test_async_select_option_turns_on_lock(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _COVER_CFG, _MODES_LIST)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()

        calls = []
        async def record(call):
            calls.append((call.service, dict(call.data)))
        hass.services.async_register("switch", "turn_on", record)
        hass.services.async_register("switch", "turn_off", record)

        # Night has lock=True; put switch in "off" state so it gets toggled
        hass.states.async_set("switch.test_lock", "off")
        hass.states.async_set("switch.test_auto_shade", "off")
        hass.states.async_set("switch.test_auto_solar_gain", "off")

        await sel.async_select_option("Night")
        assert sel._attr_current_option == "Night"
        assert any(svc == "turn_on" and d.get("entity_id") == "switch.test_lock"
                   for svc, d in calls)

    async def test_async_select_option_turns_off_lock(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _COVER_CFG, _MODES_LIST)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()

        calls = []
        async def record(call):
            calls.append((call.service, dict(call.data)))
        hass.services.async_register("switch", "turn_on", record)
        hass.services.async_register("switch", "turn_off", record)

        hass.states.async_set("switch.test_lock", "on")
        hass.states.async_set("switch.test_auto_shade", "off")
        hass.states.async_set("switch.test_auto_solar_gain", "off")

        await sel.async_select_option("Day")
        assert any(svc == "turn_off" and d.get("entity_id") == "switch.test_lock"
                   for svc, d in calls)

    async def test_async_select_option_skips_missing_switches(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _COVER_CFG, _MODES_LIST)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        # No switch states set → should not raise
        await sel.async_select_option("Day")
        assert sel._attr_current_option == "Day"


# ════════════════════════════════════════════════════════════════════════════
# CoverModesGlobalSelect
# ════════════════════════════════════════════════════════════════════════════

class TestCoverModesGlobalSelect:

    def test_hidden_modes_excluded(self, setup_hass):
        sel = CoverModesGlobalSelect(_MODES_LIST)
        assert "Hidden" not in sel._attr_options
        assert "Day" in sel._attr_options
        assert "Night" in sel._attr_options

    def test_initial_option_is_first_visible(self, setup_hass):
        sel = CoverModesGlobalSelect(_MODES_LIST)
        assert sel._attr_current_option == "Day"

    def test_icon_uses_current_option(self, setup_hass):
        hass = setup_hass
        sel = CoverModesGlobalSelect(_MODES_LIST)
        sel.hass = hass
        sel._attr_current_option = "Night"
        assert sel.icon == "mdi:moon"

    def test_extra_state_attributes_excludes_hidden(self, setup_hass):
        hass = setup_hass
        sel = CoverModesGlobalSelect(_MODES_LIST)
        sel.hass = hass
        attrs = sel.extra_state_attributes
        assert "Hidden" not in attrs["modes_list"]
        assert "Day" in attrs["modes_list"]

    def test_handle_reload_updates_options(self, setup_hass):
        hass = setup_hass
        sel = CoverModesGlobalSelect(_MODES_LIST)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()

        hass.data[DOMAIN][DATA_MODES]["Auto"] = {
            "icon": "mdi:auto", "color": "green",
            "lock": False, "auto_shade": True, "solar_gain": False, "hidden": False,
        }
        sel._handle_reload()
        assert "Auto" in sel._attr_options

    def test_handle_reload_same_options_noop(self, setup_hass):
        hass = setup_hass
        sel = CoverModesGlobalSelect(_MODES_LIST)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        original = list(sel._attr_options)
        sel._handle_reload()
        assert sel._attr_options == original

    def test_handle_reload_resets_current_when_removed(self, setup_hass):
        hass = setup_hass
        sel = CoverModesGlobalSelect(_MODES_LIST)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        sel._attr_current_option = "Night"

        # Remove Night
        del hass.data[DOMAIN][DATA_MODES]["Night"]
        # Also remove Hidden so list changes
        del hass.data[DOMAIN][DATA_MODES]["Hidden"]
        sel._handle_reload()
        assert sel._attr_current_option in sel._attr_options or sel._attr_current_option is None

    async def test_async_select_option_changes_state(self, setup_hass):
        hass = setup_hass
        sel = CoverModesGlobalSelect(_MODES_LIST)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        await sel.async_select_option("Night")
        assert sel._attr_current_option == "Night"

    def test_empty_modes_list(self, setup_hass):
        hass = setup_hass
        sel = CoverModesGlobalSelect({})
        assert sel._attr_options == []
        assert sel._attr_current_option is None
