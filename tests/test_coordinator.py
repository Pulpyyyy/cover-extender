"""Tests for CoverExtenderCoordinator business logic.

Uses the real `hass` fixture from pytest-homeassistant-custom-component.

Service call verification uses hass.services.async_register with a recording
handler — ServiceRegistry.async_call is read-only and cannot be patched.
"""
from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from custom_components.cover_extender.coordinator import CoverExtenderCoordinator
from custom_components.cover_extender.const import (
    DOMAIN,
    DATA_COVER_PROFILES,
    DATA_MODES,
    DATA_FACADES,
    DATA_MEMORY,
    DATA_SOLAR_GAIN,
)

# ── Shared test data ──────────────────────────────────────────────────────────

_PROFILES = {
    "cover.test": {
        "facade": "sud",
        "modes": {
            "Day":   40,    # fixed position, no lock
            "Night": 0,     # fixed position, lock
            "Auto":  None,  # no fixed position, auto_shade
        },
        "shade":      {"enable": True, "distance": 0.5, "max_height": 2.0,
                       "min_height": 0.0, "degrees": 90, "max_elevation": 80,
                       "min_elevation": 5, "minimum_position": 10,
                       "default_position": 100, "change_threshold": 5, "time_out": 2},
        "solar_gain": {"enable": False, "position_cold": 10, "position_solar": 80},
        "exclusion":  [],
        "angle_left":  85.0,
        "angle_right": 85.0,
    }
}

_MODES = {
    "Day":   {"lock": False, "behavior": None,         "icon": "mdi:sun",      "color": "orange", "hidden": False},
    "Night": {"lock": True,  "behavior": None,         "icon": "mdi:moon",     "color": "blue",   "hidden": False},
    "Auto":  {"lock": True,  "behavior": "auto_shade", "icon": "mdi:sun-clock","color": "amber",  "hidden": False},
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def coord(hass):
    """Coordinator with a deep-copied hass.data — mutations don't leak between tests."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].update({
        DATA_COVER_PROFILES: copy.deepcopy(_PROFILES),   # deep copy prevents test pollution
        DATA_MODES:          copy.deepcopy(_MODES),
        DATA_FACADES:        {"sud": {"azimuth": 180.0}},
        DATA_MEMORY:         {},
        DATA_SOLAR_GAIN:     {},
    })
    return CoverExtenderCoordinator(hass, "fake.yaml")


@pytest.fixture
def service_calls(hass):
    """Register recording handlers for switch.turn_on / switch.turn_off.

    Returns a list of (domain, service, data) tuples accumulated during the test.
    ServiceRegistry.async_call is read-only; registering real mock handlers is the
    correct HA testing pattern.
    """
    calls: list[tuple[str, str, dict]] = []

    async def record(call):
        calls.append((call.domain, call.service, dict(call.data)))

    for svc in ("turn_on", "turn_off"):
        hass.services.async_register("switch", svc, record)

    return calls


def _set_cover(hass, position: int) -> None:
    hass.states.async_set("cover.test", "open", {"current_position": position})


def _set_switch(hass, switch_id: str, state: str) -> None:
    hass.states.async_set(switch_id, state)


# ════════════════════════════════════════════════════════════════════════════
# _set_cover_position_impl
# ════════════════════════════════════════════════════════════════════════════

class TestSetCoverPositionImpl:

    async def test_lock_off_enqueues_command(self, coord, hass):
        _set_switch(hass, "switch.test_lock", "off")
        await coord._set_cover_position_impl(["cover.test"], 50)

        assert not coord._cover_queue.empty()
        service, data = coord._cover_queue.get_nowait()
        assert service == "set_cover_position"
        assert data == {"entity_id": "cover.test", "position": 50}

    async def test_lock_on_stores_memory(self, coord, hass):
        _set_switch(hass, "switch.test_lock", "on")
        await coord._set_cover_position_impl(["cover.test"], 75)

        assert coord._cover_queue.empty()
        assert hass.data[DOMAIN][DATA_MEMORY]["cover.test"] == 75

    async def test_multiple_covers_checked_independently(self, coord, hass):
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.other"] = (
            copy.deepcopy(_PROFILES["cover.test"])
        )
        _set_switch(hass, "switch.test_lock",  "on")
        _set_switch(hass, "switch.other_lock", "off")

        await coord._set_cover_position_impl(["cover.test", "cover.other"], 30)

        assert hass.data[DOMAIN][DATA_MEMORY].get("cover.test") == 30
        assert not coord._cover_queue.empty()


# ════════════════════════════════════════════════════════════════════════════
# _apply_mode_core
# ════════════════════════════════════════════════════════════════════════════

class TestApplyModeCore:

    async def test_unknown_mode_is_noop(self, coord, hass, service_calls):
        await coord._apply_mode_core("cover.test", "Unknown", None)
        assert service_calls == []

    async def test_day_mode_turns_lock_off(self, coord, hass, service_calls):
        _set_cover(hass, 50)
        await coord._apply_mode_core("cover.test", "Day", None)
        assert ("switch", "turn_off", {"entity_id": "switch.test_lock"}) in service_calls

    async def test_day_mode_enqueues_fixed_position(self, coord, hass, service_calls):
        _set_cover(hass, 80)
        await coord._apply_mode_core("cover.test", "Day", None)

        service, data = coord._cover_queue.get_nowait()
        assert service == "set_cover_position"
        assert data["position"] == 40

    async def test_night_mode_turns_lock_on(self, coord, hass, service_calls):
        _set_cover(hass, 50)
        await coord._apply_mode_core("cover.test", "Night", "Day")
        assert ("switch", "turn_on", {"entity_id": "switch.test_lock"}) in service_calls

    async def test_unlock_to_lock_saves_current_position(self, coord, hass, service_calls):
        _set_cover(hass, 65)
        await coord._apply_mode_core("cover.test", "Night", "Day")
        assert hass.data[DOMAIN][DATA_MEMORY]["cover.test"] == 65

    async def test_fixed_position_wins_over_memory(self, coord, hass, service_calls):
        """Night → Day: Day has a fixed position (40) → memory (55) is ignored."""
        hass.data[DOMAIN][DATA_MEMORY]["cover.test"] = 55
        _set_cover(hass, 0)
        await coord._apply_mode_core("cover.test", "Day", "Night")

        service, data = coord._cover_queue.get_nowait()
        assert service == "set_cover_position"
        assert data["position"] == 40  # fixed position wins, not memory

    async def test_lock_to_unlock_restores_memory_when_no_fixed_position(self, coord, hass, service_calls):
        """Night → mode with position=None + no lock: stored memory is restored.

        Memory restore only applies when the target mode has no fixed position.
        """
        # Add a "Free" mode: unlock, no fixed position → triggers memory restore path
        hass.data[DOMAIN][DATA_MODES]["Free"] = {
            "lock": False, "behavior": None,
            "icon": "mdi:home", "color": "white", "hidden": False,
        }
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["modes"]["Free"] = None

        hass.data[DOMAIN][DATA_MEMORY]["cover.test"] = 55
        _set_cover(hass, 0)
        await coord._apply_mode_core("cover.test", "Free", "Night")

        service, data = coord._cover_queue.get_nowait()
        assert service == "set_cover_position"
        assert data["position"] == 55
        assert "cover.test" not in hass.data[DOMAIN][DATA_MEMORY]  # cleared after restore

    async def test_exclusion_active_saves_to_memory_not_queue(self, coord, hass, service_calls):
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["exclusion"] = [
            "binary_sensor.window_open"
        ]
        hass.states.async_set("binary_sensor.window_open", "on")
        _set_cover(hass, 80)

        await coord._apply_mode_core("cover.test", "Day", None)

        assert coord._cover_queue.empty()
        assert hass.data[DOMAIN][DATA_MEMORY]["cover.test"] == 40

    async def test_auto_mode_enables_shade_and_lock(self, coord, hass, service_calls):
        _set_cover(hass, 50)
        await coord._apply_mode_core("cover.test", "Auto", "Day")

        assert ("switch", "turn_on", {"entity_id": "switch.test_auto_shade"}) in service_calls
        assert ("switch", "turn_on", {"entity_id": "switch.test_lock"}) in service_calls

    async def test_leaving_auto_mode_disables_shade(self, coord, hass, service_calls):
        _set_cover(hass, 50)
        await coord._apply_mode_core("cover.test", "Day", "Auto")

        assert ("switch", "turn_off", {"entity_id": "switch.test_auto_shade"}) in service_calls


# ════════════════════════════════════════════════════════════════════════════
# _handle_lock_off
# ════════════════════════════════════════════════════════════════════════════

class TestHandleLockOff:

    def _make_event(self, hass, old_state: str, new_state: str):
        from unittest.mock import MagicMock
        event = MagicMock()
        event.data = {
            "entity_id": "switch.test_lock",
            "old_state": MagicMock(state=old_state),
            "new_state": MagicMock(state=new_state),
        }
        return event

    def test_on_to_off_with_memory_enqueues(self, coord, hass):
        hass.data[DOMAIN][DATA_MEMORY]["cover.test"] = 45
        coord._lock_to_cover["switch.test_lock"] = "cover.test"

        coord._handle_lock_off(self._make_event(hass, "on", "off"))

        service, data = coord._cover_queue.get_nowait()
        assert service == "set_cover_position"
        assert data["position"] == 45

    def test_on_to_off_without_memory_no_command(self, coord, hass):
        coord._lock_to_cover["switch.test_lock"] = "cover.test"
        coord._handle_lock_off(self._make_event(hass, "on", "off"))
        assert coord._cover_queue.empty()

    def test_off_to_off_is_ignored(self, coord, hass):
        hass.data[DOMAIN][DATA_MEMORY]["cover.test"] = 45
        coord._lock_to_cover["switch.test_lock"] = "cover.test"
        coord._handle_lock_off(self._make_event(hass, "off", "off"))
        assert coord._cover_queue.empty()

    def test_on_to_on_is_ignored(self, coord, hass):
        hass.data[DOMAIN][DATA_MEMORY]["cover.test"] = 45
        coord._lock_to_cover["switch.test_lock"] = "cover.test"
        coord._handle_lock_off(self._make_event(hass, "on", "on"))
        assert coord._cover_queue.empty()

    def test_exclusion_active_blocks_restore(self, coord, hass):
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["exclusion"] = [
            "binary_sensor.window_open"
        ]
        hass.data[DOMAIN][DATA_MEMORY]["cover.test"] = 45
        coord._lock_to_cover["switch.test_lock"] = "cover.test"
        hass.states.async_set("binary_sensor.window_open", "on")

        coord._handle_lock_off(self._make_event(hass, "on", "off"))
        assert coord._cover_queue.empty()


# ════════════════════════════════════════════════════════════════════════════
# _handle_solar_gain_switch_on
# ════════════════════════════════════════════════════════════════════════════

class TestHandleSolarGainSwitchOn:

    def _make_event(self, old_state: str, new_state: str):
        from unittest.mock import MagicMock
        event = MagicMock()
        event.data = {
            "entity_id": "switch.test_auto_solar_gain",
            "old_state": MagicMock(state=old_state),
            "new_state": MagicMock(state=new_state),
        }
        return event

    def test_off_to_on_calls_apply_solar_gain(self, coord, hass):
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["solar_gain"]["enable"] = True
        with patch.object(coord, "_apply_solar_gain") as mock_apply:
            coord._handle_solar_gain_switch_on(self._make_event("off", "on"))
            mock_apply.assert_called_once_with(
                "cover.test",
                hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"],
            )

    def test_on_to_on_is_ignored(self, coord, hass):
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["solar_gain"]["enable"] = True
        with patch.object(coord, "_apply_solar_gain") as mock_apply:
            coord._handle_solar_gain_switch_on(self._make_event("on", "on"))
            mock_apply.assert_not_called()

    def test_off_to_off_is_ignored(self, coord, hass):
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["solar_gain"]["enable"] = True
        with patch.object(coord, "_apply_solar_gain") as mock_apply:
            coord._handle_solar_gain_switch_on(self._make_event("off", "off"))
            mock_apply.assert_not_called()

    def test_solar_gain_disabled_cover_is_skipped(self, coord, hass):
        """Cover with solar_gain.enable=False must not trigger even on switch ON."""
        # solar_gain.enable is False in the deep-copied _PROFILES (not mutated by other tests)
        assert hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["solar_gain"]["enable"] is False
        with patch.object(coord, "_apply_solar_gain") as mock_apply:
            coord._handle_solar_gain_switch_on(self._make_event("off", "on"))
            mock_apply.assert_not_called()
