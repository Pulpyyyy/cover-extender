"""Tests for switch entity classes."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.cover_extender.switch import (
    CoverLockSwitch,
    CoverShadingAutoSwitch,
    CoverSolarGainAutoSwitch,
)
from custom_components.cover_extender.const import DOMAIN, DATA_COVER_PROFILES


@pytest.fixture
def setup_hass(hass):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_COVER_PROFILES] = {"cover.test": {}}
    return hass


# ════════════════════════════════════════════════════════════════════════════
# CoverLockSwitch
# ════════════════════════════════════════════════════════════════════════════

class TestCoverLockSwitch:

    def test_entity_id_format(self, setup_hass):
        sw = CoverLockSwitch("cover.volet_sam")
        assert sw.entity_id == "switch.volet_sam_lock"

    def test_initial_state_is_off(self, setup_hass):
        sw = CoverLockSwitch("cover.test")
        assert sw._attr_is_on is False

    def test_icon_off(self, setup_hass):
        sw = CoverLockSwitch("cover.test")
        sw._attr_is_on = False
        assert sw.icon == "mdi:lock-open-variant"

    def test_icon_on(self, setup_hass):
        sw = CoverLockSwitch("cover.test")
        sw._attr_is_on = True
        assert sw.icon == "mdi:lock"

    def test_extra_state_attributes_off(self, setup_hass):
        sw = CoverLockSwitch("cover.test")
        sw._attr_is_on = False
        attrs = sw.extra_state_attributes
        assert "disabled" in attrs["icon_color"]

    def test_extra_state_attributes_on(self, setup_hass):
        sw = CoverLockSwitch("cover.test")
        sw._attr_is_on = True
        attrs = sw.extra_state_attributes
        assert "primary" in attrs["icon_color"]

    async def test_turn_on(self, setup_hass, hass):
        sw = CoverLockSwitch("cover.test")
        sw.hass = hass
        sw.entity_id = "switch.test_lock"
        sw.async_write_ha_state = MagicMock()
        hass.states.async_set("switch.test_lock", "off")
        await sw.async_turn_on()
        assert sw._attr_is_on is True

    async def test_turn_off(self, setup_hass, hass):
        sw = CoverLockSwitch("cover.test")
        sw.hass = hass
        sw.entity_id = "switch.test_lock"
        sw.async_write_ha_state = MagicMock()
        hass.states.async_set("switch.test_lock", "on")
        await sw.async_turn_off()
        assert sw._attr_is_on is False


# ════════════════════════════════════════════════════════════════════════════
# CoverShadingAutoSwitch
# ════════════════════════════════════════════════════════════════════════════

class TestCoverShadingAutoSwitch:

    def test_entity_id_format(self, setup_hass):
        sw = CoverShadingAutoSwitch("cover.test")
        assert sw.entity_id == "switch.test_auto_shade"

    def test_initial_state_is_off(self, setup_hass):
        sw = CoverShadingAutoSwitch("cover.test")
        assert sw._attr_is_on is False

    def test_icon_off(self, setup_hass):
        sw = CoverShadingAutoSwitch("cover.test")
        sw._attr_is_on = False
        assert sw.icon == "mdi:sun-clock-outline"

    def test_icon_on(self, setup_hass):
        sw = CoverShadingAutoSwitch("cover.test")
        sw._attr_is_on = True
        assert sw.icon == "mdi:sun-clock"

    async def test_turn_on_sets_state(self, setup_hass, hass):
        sw = CoverShadingAutoSwitch("cover.test")
        sw.hass = hass
        sw.entity_id = "switch.test_auto_shade"
        sw.async_write_ha_state = MagicMock()
        hass.states.async_set("switch.test_auto_shade", "off")
        await sw.async_turn_on()
        assert sw._attr_is_on is True

    async def test_turn_off_sets_state(self, setup_hass, hass):
        sw = CoverShadingAutoSwitch("cover.test")
        sw.hass = hass
        sw.entity_id = "switch.test_auto_shade"
        sw.async_write_ha_state = MagicMock()
        hass.states.async_set("switch.test_auto_shade", "on")
        await sw.async_turn_off()
        assert sw._attr_is_on is False


# ════════════════════════════════════════════════════════════════════════════
# CoverSolarGainAutoSwitch
# ════════════════════════════════════════════════════════════════════════════

class TestCoverSolarGainAutoSwitch:

    def test_entity_id_format(self, setup_hass):
        sw = CoverSolarGainAutoSwitch("cover.test")
        assert sw.entity_id == "switch.test_auto_solar_gain"

    def test_initial_state_is_off(self, setup_hass):
        sw = CoverSolarGainAutoSwitch("cover.test")
        assert sw._attr_is_on is False

    def test_icon_off(self, setup_hass):
        sw = CoverSolarGainAutoSwitch("cover.test")
        sw._attr_is_on = False
        assert sw.icon == "mdi:thermometer-off"

    def test_icon_on(self, setup_hass):
        sw = CoverSolarGainAutoSwitch("cover.test")
        sw._attr_is_on = True
        assert sw.icon == "mdi:thermometer-check"

    def test_extra_state_attributes_on(self, setup_hass):
        sw = CoverSolarGainAutoSwitch("cover.test")
        sw._attr_is_on = True
        assert "primary" in sw.extra_state_attributes["icon_color"]

    async def test_turn_on_sets_state(self, setup_hass, hass):
        sw = CoverSolarGainAutoSwitch("cover.test")
        sw.hass = hass
        sw.entity_id = "switch.test_auto_solar_gain"
        sw.async_write_ha_state = MagicMock()
        hass.states.async_set("switch.test_auto_solar_gain", "off")
        await sw.async_turn_on()
        assert sw._attr_is_on is True

    async def test_turn_off_sets_state(self, setup_hass, hass):
        sw = CoverSolarGainAutoSwitch("cover.test")
        sw.hass = hass
        sw.entity_id = "switch.test_auto_solar_gain"
        sw.async_write_ha_state = MagicMock()
        hass.states.async_set("switch.test_auto_solar_gain", "on")
        await sw.async_turn_off()
        assert sw._attr_is_on is False
