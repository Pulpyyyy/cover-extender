"""Tests for async_added_to_hass and platform reload signal handlers."""
from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.cover_extender.binary_sensor import (
    CoverSunFacingBinarySensor,
    CoverEnableAutoShadeBinarySensor,
    CoverEnableSolarGainBinarySensor,
)
from custom_components.cover_extender.switch import (
    CoverLockSwitch,
    CoverShadingAutoSwitch,
    CoverSolarGainAutoSwitch,
    async_setup_entry as switch_setup_entry,
)
from custom_components.cover_extender.select import (
    CoverModeSelect,
    CoverModesGlobalSelect,
    async_setup_entry as select_setup_entry,
)
from custom_components.cover_extender.binary_sensor import (
    async_setup_entry as binary_sensor_setup_entry,
)
from custom_components.cover_extender.const import (
    DOMAIN,
    DATA_COVER_PROFILES,
    DATA_MODES,
    DATA_SHOW_ENTITIES,
    DATA_SWITCH_COVER_IDS,
    DATA_SWITCH_AUTO_SHADE_IDS,
    DATA_SWITCH_AUTO_SOLAR_GAIN_IDS,
    DATA_SELECT_COVER_IDS,
    DATA_BINARY_SENSOR_SUN_FACING_IDS,
    DATA_BINARY_SENSOR_AUTO_SHADE_IDS,
    DATA_BINARY_SENSOR_AUTO_SOLAR_GAIN_IDS,
    ATTR_SUN_FACING,
    SIGNAL_COVER_RELOAD,
)

_MODES = {
    "Day":   {"icon": "mdi:sun", "color": "orange", "lock": False, "behavior": None, "hidden": False},
    "Night": {"icon": "mdi:moon","color": "blue",   "lock": True,  "behavior": None, "hidden": False},
}

_PROFILES = {
    "cover.test": {
        "facade": "sud",
        "modes": {"Day": 40, "Night": 0},
        "shade": {"enable": True},
        "solar_gain": {"enable": True},
        "exclusion": [],
    }
}


@pytest.fixture
def setup_hass(hass):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_COVER_PROFILES] = copy.deepcopy(_PROFILES)
    hass.data[DOMAIN][DATA_MODES] = dict(_MODES)
    hass.data[DOMAIN][DATA_SHOW_ENTITIES] = {
        "sun_facing": True, "auto_shade": True, "solar_gain": True
    }
    return hass


# ════════════════════════════════════════════════════════════════════════════
# Switch async_added_to_hass
# ════════════════════════════════════════════════════════════════════════════

class TestSwitchAddedToHass:

    async def _make_switch(self, cls, hass, last_state_str=None):
        sw = cls("cover.test")
        sw.hass = hass
        sw.async_write_ha_state = MagicMock()
        if last_state_str is not None:
            mock_state = MagicMock()
            mock_state.state = last_state_str
            sw.async_get_last_state = AsyncMock(return_value=mock_state)
        else:
            sw.async_get_last_state = AsyncMock(return_value=None)
        return sw

    async def test_lock_restores_on_state(self, hass):
        sw = await self._make_switch(CoverLockSwitch, hass, "on")
        await sw.async_added_to_hass()
        assert sw._attr_is_on is True
        sw.async_write_ha_state.assert_called_once()

    async def test_lock_restores_off_state(self, hass):
        sw = await self._make_switch(CoverLockSwitch, hass, "off")
        await sw.async_added_to_hass()
        assert sw._attr_is_on is False
        sw.async_write_ha_state.assert_called_once()

    async def test_lock_no_prior_state_stays_off(self, hass):
        sw = await self._make_switch(CoverLockSwitch, hass)
        await sw.async_added_to_hass()
        assert sw._attr_is_on is False
        sw.async_write_ha_state.assert_not_called()

    async def test_auto_shade_restores_on_state(self, hass):
        sw = await self._make_switch(CoverShadingAutoSwitch, hass, "on")
        await sw.async_added_to_hass()
        assert sw._attr_is_on is True

    async def test_auto_shade_no_prior_state(self, hass):
        sw = await self._make_switch(CoverShadingAutoSwitch, hass)
        await sw.async_added_to_hass()
        assert sw._attr_is_on is False
        sw.async_write_ha_state.assert_not_called()

    async def test_solar_gain_restores_on_state(self, hass):
        sw = await self._make_switch(CoverSolarGainAutoSwitch, hass, "on")
        await sw.async_added_to_hass()
        assert sw._attr_is_on is True

    async def test_solar_gain_no_prior_state(self, hass):
        sw = await self._make_switch(CoverSolarGainAutoSwitch, hass)
        await sw.async_added_to_hass()
        sw.async_write_ha_state.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# Select async_added_to_hass
# ════════════════════════════════════════════════════════════════════════════

class TestSelectAddedToHass:

    async def test_cover_mode_select_restores_valid_option(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _PROFILES["cover.test"], _MODES)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        sel.async_on_remove = MagicMock()

        mock_state = MagicMock()
        mock_state.state = "Night"
        sel.async_get_last_state = AsyncMock(return_value=mock_state)

        await sel.async_added_to_hass()
        assert sel._attr_current_option == "Night"
        sel.async_write_ha_state.assert_called_once()

    async def test_cover_mode_select_invalid_option_not_restored(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _PROFILES["cover.test"], _MODES)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        sel.async_on_remove = MagicMock()

        mock_state = MagicMock()
        mock_state.state = "Ghost"
        sel.async_get_last_state = AsyncMock(return_value=mock_state)

        await sel.async_added_to_hass()
        assert sel._attr_current_option == "Day"  # unchanged (first option)
        sel.async_write_ha_state.assert_not_called()

    async def test_cover_mode_select_no_prior_state(self, setup_hass):
        hass = setup_hass
        sel = CoverModeSelect("cover.test", _PROFILES["cover.test"], _MODES)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        sel.async_on_remove = MagicMock()
        sel.async_get_last_state = AsyncMock(return_value=None)

        await sel.async_added_to_hass()
        sel.async_write_ha_state.assert_not_called()
        sel.async_on_remove.assert_called_once()

    async def test_global_modes_select_restores_valid_option(self, setup_hass):
        hass = setup_hass
        sel = CoverModesGlobalSelect(_MODES)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        sel.async_on_remove = MagicMock()

        mock_state = MagicMock()
        mock_state.state = "Night"
        sel.async_get_last_state = AsyncMock(return_value=mock_state)

        await sel.async_added_to_hass()
        assert sel._attr_current_option == "Night"

    async def test_global_modes_select_no_prior_state(self, setup_hass):
        hass = setup_hass
        sel = CoverModesGlobalSelect(_MODES)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()
        sel.async_on_remove = MagicMock()
        sel.async_get_last_state = AsyncMock(return_value=None)

        await sel.async_added_to_hass()
        sel.async_on_remove.assert_called_once()


# ════════════════════════════════════════════════════════════════════════════
# Binary sensor async_added_to_hass
# ════════════════════════════════════════════════════════════════════════════

class TestBinarySensorAddedToHass:

    async def test_sun_facing_reads_existing_cover_state(self, hass):
        hass.states.async_set("cover.test", "open", {ATTR_SUN_FACING: True})
        bs = CoverSunFacingBinarySensor("cover.test")
        bs.hass = hass
        bs.async_write_ha_state = MagicMock()
        bs.async_on_remove = MagicMock()

        await bs.async_added_to_hass()
        assert bs._attr_is_on is True
        bs.async_write_ha_state.assert_called_once()
        bs.async_on_remove.assert_called_once()

    async def test_sun_facing_no_cover_state(self, hass):
        bs = CoverSunFacingBinarySensor("cover.test")
        bs.hass = hass
        bs.async_write_ha_state = MagicMock()
        bs.async_on_remove = MagicMock()

        await bs.async_added_to_hass()
        bs.async_write_ha_state.assert_not_called()
        bs.async_on_remove.assert_called_once()

    async def test_sun_facing_cover_state_no_attr(self, hass):
        hass.states.async_set("cover.test", "open", {})
        bs = CoverSunFacingBinarySensor("cover.test")
        bs.hass = hass
        bs.async_write_ha_state = MagicMock()
        bs.async_on_remove = MagicMock()

        await bs.async_added_to_hass()
        bs.async_write_ha_state.assert_not_called()

    async def test_auto_shade_reads_switch_state_on(self, hass):
        hass.states.async_set("switch.test_auto_shade", "on")
        bs = CoverEnableAutoShadeBinarySensor("cover.test", False)
        bs.hass = hass
        bs.async_write_ha_state = MagicMock()
        bs.async_on_remove = MagicMock()

        await bs.async_added_to_hass()
        assert bs._attr_is_on is True
        bs.async_write_ha_state.assert_called_once()

    async def test_auto_shade_reads_switch_state_off(self, hass):
        hass.states.async_set("switch.test_auto_shade", "off")
        bs = CoverEnableAutoShadeBinarySensor("cover.test", True)
        bs.hass = hass
        bs.async_write_ha_state = MagicMock()
        bs.async_on_remove = MagicMock()

        await bs.async_added_to_hass()
        assert bs._attr_is_on is False

    async def test_auto_shade_no_switch_state(self, hass):
        bs = CoverEnableAutoShadeBinarySensor("cover.test", False)
        bs.hass = hass
        bs.async_write_ha_state = MagicMock()
        bs.async_on_remove = MagicMock()

        await bs.async_added_to_hass()
        bs.async_write_ha_state.assert_not_called()
        bs.async_on_remove.assert_called_once()

    async def test_solar_gain_reads_switch_state_on(self, hass):
        hass.states.async_set("switch.test_auto_solar_gain", "on")
        bs = CoverEnableSolarGainBinarySensor("cover.test", False)
        bs.hass = hass
        bs.async_write_ha_state = MagicMock()
        bs.async_on_remove = MagicMock()

        await bs.async_added_to_hass()
        assert bs._attr_is_on is True

    async def test_solar_gain_no_switch_state(self, hass):
        bs = CoverEnableSolarGainBinarySensor("cover.test", False)
        bs.hass = hass
        bs.async_write_ha_state = MagicMock()
        bs.async_on_remove = MagicMock()

        await bs.async_added_to_hass()
        bs.async_write_ha_state.assert_not_called()

    async def test_auto_shade_switch_change_tracked(self, hass):
        """After async_added_to_hass, a switch state change updates the sensor."""
        hass.states.async_set("switch.test_auto_shade", "off")
        bs = CoverEnableAutoShadeBinarySensor("cover.test", False)
        bs.hass = hass
        bs.async_write_ha_state = MagicMock()
        bs.async_on_remove = MagicMock()

        await bs.async_added_to_hass()
        assert bs._attr_is_on is False

        # Trigger switch turn on
        hass.states.async_set("switch.test_auto_shade", "on")
        await hass.async_block_till_done()

        assert bs._attr_is_on is True

    async def test_solar_gain_switch_change_tracked(self, hass):
        hass.states.async_set("switch.test_auto_solar_gain", "off")
        bs = CoverEnableSolarGainBinarySensor("cover.test", False)
        bs.hass = hass
        bs.async_write_ha_state = MagicMock()
        bs.async_on_remove = MagicMock()

        await bs.async_added_to_hass()

        hass.states.async_set("switch.test_auto_solar_gain", "on")
        await hass.async_block_till_done()

        assert bs._attr_is_on is True


# ════════════════════════════════════════════════════════════════════════════
# Platform reload signal — switch
# ════════════════════════════════════════════════════════════════════════════

class TestSwitchPlatformReload:

    @pytest.fixture
    def mock_entry(self, setup_hass):
        from pytest_homeassistant_custom_component.common import MockConfigEntry
        entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, unique_id="test_reload")
        entry.add_to_hass(setup_hass)
        return entry

    async def test_new_cover_added_to_tracking_set(self, setup_hass, mock_entry):
        hass = setup_hass
        entities = []

        await switch_setup_entry(hass, mock_entry, lambda e: entities.extend(e))
        initial_ids = set(hass.data[DOMAIN][DATA_SWITCH_COVER_IDS])

        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.new"] = {}
        async_dispatcher_send(hass, SIGNAL_COVER_RELOAD)

        assert "cover.new" in hass.data[DOMAIN][DATA_SWITCH_COVER_IDS]

    async def test_removed_cover_cleared_from_tracking_set(self, setup_hass, mock_entry):
        hass = setup_hass
        entities = []

        await switch_setup_entry(hass, mock_entry, lambda e: entities.extend(e))
        assert "cover.test" in hass.data[DOMAIN][DATA_SWITCH_COVER_IDS]

        del hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]
        async_dispatcher_send(hass, SIGNAL_COVER_RELOAD)

        assert "cover.test" not in hass.data[DOMAIN][DATA_SWITCH_COVER_IDS]

    async def test_auto_shade_added_when_shade_enabled(self, setup_hass, mock_entry):
        hass = setup_hass
        entities = []

        # Initially shade disabled
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["shade"]["enable"] = False
        await switch_setup_entry(hass, mock_entry, lambda e: entities.extend(e))

        # Enable shade and reload
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["shade"]["enable"] = True
        async_dispatcher_send(hass, SIGNAL_COVER_RELOAD)

        assert "cover.test" in hass.data[DOMAIN][DATA_SWITCH_AUTO_SHADE_IDS]

    async def test_auto_shade_removed_when_shade_disabled(self, setup_hass, mock_entry):
        hass = setup_hass
        entities = []

        # Initially shade enabled
        await switch_setup_entry(hass, mock_entry, lambda e: entities.extend(e))
        assert "cover.test" in hass.data[DOMAIN][DATA_SWITCH_AUTO_SHADE_IDS]

        # Disable shade and reload
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["shade"]["enable"] = False
        async_dispatcher_send(hass, SIGNAL_COVER_RELOAD)

        assert "cover.test" not in hass.data[DOMAIN][DATA_SWITCH_AUTO_SHADE_IDS]

    async def test_solar_gain_added_on_reload(self, setup_hass, mock_entry):
        hass = setup_hass
        entities = []

        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["solar_gain"]["enable"] = False
        await switch_setup_entry(hass, mock_entry, lambda e: entities.extend(e))

        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["solar_gain"]["enable"] = True
        async_dispatcher_send(hass, SIGNAL_COVER_RELOAD)

        assert "cover.test" in hass.data[DOMAIN][DATA_SWITCH_AUTO_SOLAR_GAIN_IDS]

    async def test_solar_gain_removed_on_reload(self, setup_hass, mock_entry):
        hass = setup_hass
        entities = []

        await switch_setup_entry(hass, mock_entry, lambda e: entities.extend(e))
        assert "cover.test" in hass.data[DOMAIN][DATA_SWITCH_AUTO_SOLAR_GAIN_IDS]

        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["solar_gain"]["enable"] = False
        async_dispatcher_send(hass, SIGNAL_COVER_RELOAD)

        assert "cover.test" not in hass.data[DOMAIN][DATA_SWITCH_AUTO_SOLAR_GAIN_IDS]


# ════════════════════════════════════════════════════════════════════════════
# Platform reload signal — select
# ════════════════════════════════════════════════════════════════════════════

class TestSelectPlatformReload:

    @pytest.fixture
    def mock_entry(self, setup_hass):
        from pytest_homeassistant_custom_component.common import MockConfigEntry
        entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, unique_id="test_select_reload")
        entry.add_to_hass(setup_hass)
        return entry

    async def test_new_cover_added_to_tracking_set(self, setup_hass, mock_entry):
        hass = setup_hass
        entities = []

        await select_setup_entry(hass, mock_entry, lambda e: entities.extend(e))

        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.new"] = {"modes": {"Day": 40}}
        async_dispatcher_send(hass, SIGNAL_COVER_RELOAD)

        assert "cover.new" in hass.data[DOMAIN][DATA_SELECT_COVER_IDS]

    async def test_removed_cover_cleared_from_tracking_set(self, setup_hass, mock_entry):
        hass = setup_hass
        entities = []

        await select_setup_entry(hass, mock_entry, lambda e: entities.extend(e))
        assert "cover.test" in hass.data[DOMAIN][DATA_SELECT_COVER_IDS]

        del hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]
        async_dispatcher_send(hass, SIGNAL_COVER_RELOAD)

        assert "cover.test" not in hass.data[DOMAIN][DATA_SELECT_COVER_IDS]


# ════════════════════════════════════════════════════════════════════════════
# Platform reload signal — binary_sensor
# ════════════════════════════════════════════════════════════════════════════

class TestBinarySensorPlatformReload:

    @pytest.fixture
    def mock_entry(self, setup_hass):
        from pytest_homeassistant_custom_component.common import MockConfigEntry
        entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, unique_id="test_bs_reload")
        entry.add_to_hass(setup_hass)
        return entry

    async def test_sun_facing_added_on_reload(self, setup_hass, mock_entry):
        hass = setup_hass
        entities = []
        hass.data[DOMAIN][DATA_SHOW_ENTITIES] = {"sun_facing": False, "auto_shade": False, "solar_gain": False}

        await binary_sensor_setup_entry(hass, mock_entry, lambda e: entities.extend(e))

        # Enable sun_facing and add facade to profile
        hass.data[DOMAIN][DATA_SHOW_ENTITIES] = {"sun_facing": True, "auto_shade": False, "solar_gain": False}
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["facade"] = "sud"
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.new"] = {"facade": "sud"}
        async_dispatcher_send(hass, SIGNAL_COVER_RELOAD)

        assert "cover.new" in hass.data[DOMAIN][DATA_BINARY_SENSOR_SUN_FACING_IDS]

    async def test_auto_shade_removed_on_reload(self, setup_hass, mock_entry):
        hass = setup_hass
        entities = []

        await binary_sensor_setup_entry(hass, mock_entry, lambda e: entities.extend(e))
        assert "cover.test" in hass.data[DOMAIN][DATA_BINARY_SENSOR_AUTO_SHADE_IDS]

        # Remove cover from profiles
        del hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]
        async_dispatcher_send(hass, SIGNAL_COVER_RELOAD)

        assert "cover.test" not in hass.data[DOMAIN][DATA_BINARY_SENSOR_AUTO_SHADE_IDS]
