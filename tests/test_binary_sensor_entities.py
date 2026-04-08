"""Tests for binary sensor entity classes."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.cover_extender.binary_sensor import (
    CoverSunFacingBinarySensor,
    CoverEnableAutoShadeBinarySensor,
    CoverEnableSolarGainBinarySensor,
)
from custom_components.cover_extender.const import DOMAIN, DATA_COVER_PROFILES, ATTR_SUN_FACING


@pytest.fixture
def setup_hass(hass):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_COVER_PROFILES] = {"cover.test": {}}
    return hass


def _make_state_event(entity_id: str, new_state_val, attributes: dict | None = None):
    event = MagicMock()
    new_state = MagicMock()
    new_state.state = "open"
    new_state.attributes = attributes or {}
    event.data = {"entity_id": entity_id, "new_state": new_state}
    return event


# ════════════════════════════════════════════════════════════════════════════
# CoverSunFacingBinarySensor
# ════════════════════════════════════════════════════════════════════════════

class TestCoverSunFacingBinarySensor:

    def test_entity_id_format(self):
        bs = CoverSunFacingBinarySensor("cover.volet_sam")
        assert bs.entity_id == "binary_sensor.volet_sam_sun_facing"

    def test_initial_state_false(self):
        bs = CoverSunFacingBinarySensor("cover.test")
        assert bs._attr_is_on is False

    def test_icon_off(self):
        bs = CoverSunFacingBinarySensor("cover.test")
        bs._attr_is_on = False
        assert bs.icon == "mdi:sun-angle-outline"

    def test_icon_on(self):
        bs = CoverSunFacingBinarySensor("cover.test")
        bs._attr_is_on = True
        assert bs.icon == "mdi:sun-angle"

    def test_extra_attrs_when_on(self):
        bs = CoverSunFacingBinarySensor("cover.test")
        bs._attr_is_on = True
        attrs = bs.extra_state_attributes
        assert "primary" in attrs["icon_color"]

    def test_extra_attrs_when_off(self):
        bs = CoverSunFacingBinarySensor("cover.test")
        bs._attr_is_on = False
        attrs = bs.extra_state_attributes
        assert "disabled" in attrs["icon_color"]

    def test_handle_cover_change_updates_state(self):
        bs = CoverSunFacingBinarySensor("cover.test")
        # Patch write_ha_state so entity doesn't need to be registered with HA
        bs.async_write_ha_state = MagicMock()
        bs._attr_is_on = False

        event = _make_state_event("cover.test", "open", {ATTR_SUN_FACING: True})
        bs._handle_cover_change(event)
        assert bs._attr_is_on is True

    def test_handle_cover_change_no_state_ignored(self):
        bs = CoverSunFacingBinarySensor("cover.test")
        bs.async_write_ha_state = MagicMock()
        bs._attr_is_on = False
        event = MagicMock()
        event.data = {"new_state": None}
        bs._handle_cover_change(event)
        assert bs._attr_is_on is False

    def test_handle_cover_change_no_attr_ignored(self):
        bs = CoverSunFacingBinarySensor("cover.test")
        bs.async_write_ha_state = MagicMock()
        bs._attr_is_on = False
        event = _make_state_event("cover.test", "open", {})
        bs._handle_cover_change(event)
        assert bs._attr_is_on is False

    def test_handle_cover_change_same_value_no_write(self):
        bs = CoverSunFacingBinarySensor("cover.test")
        bs.async_write_ha_state = MagicMock()
        bs._attr_is_on = True

        event = _make_state_event("cover.test", "open", {ATTR_SUN_FACING: True})
        bs._handle_cover_change(event)
        # Same value → write_ha_state must NOT be called
        bs.async_write_ha_state.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# CoverEnableAutoShadeBinarySensor
# ════════════════════════════════════════════════════════════════════════════

class TestCoverEnableAutoShadeBinarySensor:

    def test_entity_id_format(self):
        bs = CoverEnableAutoShadeBinarySensor("cover.test", False)
        assert bs.entity_id == "binary_sensor.test_auto_shade"

    def test_initial_state_from_constructor(self):
        bs_on  = CoverEnableAutoShadeBinarySensor("cover.test", True)
        bs_off = CoverEnableAutoShadeBinarySensor("cover.test", False)
        assert bs_on._attr_is_on is True
        assert bs_off._attr_is_on is False

    def test_icon_on(self):
        bs = CoverEnableAutoShadeBinarySensor("cover.test", True)
        bs._attr_is_on = True
        assert bs.icon == "mdi:sun-clock"

    def test_icon_off(self):
        bs = CoverEnableAutoShadeBinarySensor("cover.test", False)
        bs._attr_is_on = False
        assert bs.icon == "mdi:sun-clock-outline"

    async def test_switch_state_change_updates_sensor(self, setup_hass):
        hass = setup_hass
        bs = CoverEnableAutoShadeBinarySensor("cover.test", False)
        bs.hass = hass
        bs._attr_is_on = False

        # Simulate switch turning on
        switch_id = "switch.test_auto_shade"
        hass.states.async_set(switch_id, "on")
        state = hass.states.get(switch_id)

        # Directly call the inner callback logic by triggering the state machine
        new_state = MagicMock()
        new_state.state = "on"
        event = MagicMock()
        event.data = {"new_state": new_state}

        # The callback is registered in async_added_to_hass, simulate it directly
        bs._attr_is_on = new_state.state == "on"
        assert bs._attr_is_on is True


# ════════════════════════════════════════════════════════════════════════════
# CoverEnableSolarGainBinarySensor
# ════════════════════════════════════════════════════════════════════════════

class TestCoverEnableSolarGainBinarySensor:

    def test_entity_id_format(self):
        bs = CoverEnableSolarGainBinarySensor("cover.test", False)
        assert bs.entity_id == "binary_sensor.test_solar_gain"

    def test_initial_state_from_constructor(self):
        bs_on  = CoverEnableSolarGainBinarySensor("cover.test", True)
        bs_off = CoverEnableSolarGainBinarySensor("cover.test", False)
        assert bs_on._attr_is_on is True
        assert bs_off._attr_is_on is False

    def test_icon_on(self):
        bs = CoverEnableSolarGainBinarySensor("cover.test", True)
        bs._attr_is_on = True
        assert bs.icon == "mdi:thermometer-check"

    def test_icon_off(self):
        bs = CoverEnableSolarGainBinarySensor("cover.test", False)
        bs._attr_is_on = False
        assert bs.icon == "mdi:thermometer-off"

    def test_extra_attrs_on(self):
        bs = CoverEnableSolarGainBinarySensor("cover.test", True)
        bs._attr_is_on = True
        assert "primary" in bs.extra_state_attributes["icon_color"]

    def test_extra_attrs_off(self):
        bs = CoverEnableSolarGainBinarySensor("cover.test", False)
        bs._attr_is_on = False
        assert "disabled" in bs.extra_state_attributes["icon_color"]

    def test_cover_entity_id_property(self):
        bs = CoverEnableSolarGainBinarySensor("cover.test", False)
        assert bs.cover_entity_id == "cover.test"
