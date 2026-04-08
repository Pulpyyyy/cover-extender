"""Extended coordinator tests covering service handlers and event callbacks."""
from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.cover_extender.coordinator import CoverExtenderCoordinator
from custom_components.cover_extender.const import (
    DOMAIN,
    DATA_COVER_PROFILES,
    DATA_MODES,
    DATA_FACADES,
    DATA_MEMORY,
    DATA_SOLAR_GAIN,
    EVENT_SHADE_APPLIED,
)

# ── Shared test data (mirrors test_coordinator.py) ────────────────────────────

_PROFILES = {
    "cover.test": {
        "facade": "sud",
        "modes": {"Day": 40, "Night": 0, "Auto": None},
        "shade": {
            "enable": True,
            "distance": 0.5,
            "max_height": 2.0,
            "min_height": 0.0,
            "degrees": 90,
            "max_elevation": 80,
            "min_elevation": 5,
            "minimum_position": 10,
            "default_position": 100,
            "change_threshold": 5,
            "time_out": 2,
        },
        "solar_gain": {"enable": False, "position_cold": 10, "position_solar": 80},
        "exclusion": [],
        "angle_left": 85.0,
        "angle_right": 85.0,
    }
}

_MODES = {
    "Day":   {"lock": False, "auto_shade": False, "solar_gain": False, "icon": "mdi:sun",      "color": "orange", "hidden": False},
    "Night": {"lock": True,  "auto_shade": False, "solar_gain": False, "icon": "mdi:moon",     "color": "blue",   "hidden": False},
    "Auto":  {"lock": True,  "auto_shade": True,  "solar_gain": False, "icon": "mdi:sun-clock","color": "amber",  "hidden": False},
    "Solar": {"lock": True,  "auto_shade": False, "solar_gain": True,  "icon": "mdi:thermometer","color": "red",  "hidden": False},
}


@pytest.fixture
def coord(hass):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].update({
        DATA_COVER_PROFILES: copy.deepcopy(_PROFILES),
        DATA_MODES:          copy.deepcopy(_MODES),
        DATA_FACADES:        {"sud": {"azimuth": 180.0}},
        DATA_MEMORY:         {},
        DATA_SOLAR_GAIN:     {},
    })
    return CoverExtenderCoordinator(hass, "fake.yaml")


@pytest.fixture
def service_calls(hass):
    calls: list[tuple[str, str, dict]] = []

    async def record(call):
        calls.append((call.domain, call.service, dict(call.data)))

    for svc in ("turn_on", "turn_off"):
        hass.services.async_register("switch", svc, record)
    return calls


def _set_switch(hass, switch_id: str, state: str) -> None:
    hass.states.async_set(switch_id, state)


def _set_cover(hass, position: int, state: str = "open") -> None:
    hass.states.async_set("cover.test", state, {"current_position": position})


def _make_event(entity_id: str, old_state: str, new_state: str):
    event = MagicMock()
    event.data = {
        "entity_id": entity_id,
        "old_state": MagicMock(state=old_state),
        "new_state": MagicMock(state=new_state),
    }
    return event


# ════════════════════════════════════════════════════════════════════════════
# _apply_shade
# ════════════════════════════════════════════════════════════════════════════

class TestApplyShade:

    def test_auto_shade_switch_off_skips(self, coord, hass):
        _set_switch(hass, "switch.test_auto_shade", "off")
        _set_cover(hass, 50)
        coord._apply_shade("cover.test", hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"])
        assert coord._cover_queue.empty()

    def test_auto_shade_switch_missing_skips(self, coord, hass):
        # switch not in state machine at all
        _set_cover(hass, 50)
        coord._apply_shade("cover.test", hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"])
        assert coord._cover_queue.empty()

    def test_cover_unavailable_skips(self, coord, hass):
        _set_switch(hass, "switch.test_auto_shade", "on")
        hass.states.async_set("cover.test", "unavailable", {})
        coord._apply_shade("cover.test", hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"])
        assert coord._cover_queue.empty()

    def test_auto_shade_on_enqueues_when_should_update(self, coord, hass):
        _set_switch(hass, "switch.test_auto_shade", "on")
        # No existing cover state → compute_shade_sync returns should_update=True
        hass.states.async_set("sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 45.0})

        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]
        with patch(
            "custom_components.cover_extender.coordinator.compute_shade_sync",
            return_value=(30, True),
        ):
            coord._apply_shade("cover.test", cfg)

        assert not coord._cover_queue.empty()
        service, data = coord._cover_queue.get_nowait()
        assert service == "set_cover_position"
        assert data["position"] == 30

    def test_auto_shade_on_no_enqueue_when_no_update(self, coord, hass):
        _set_switch(hass, "switch.test_auto_shade", "on")
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]
        with patch(
            "custom_components.cover_extender.coordinator.compute_shade_sync",
            return_value=(30, False),
        ):
            coord._apply_shade("cover.test", cfg)

        assert coord._cover_queue.empty()

    async def test_shade_applied_event_fired(self, coord, hass):
        _set_switch(hass, "switch.test_auto_shade", "on")
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]
        fired = []
        hass.bus.async_listen(EVENT_SHADE_APPLIED, lambda e: fired.append(e))

        with patch(
            "custom_components.cover_extender.coordinator.compute_shade_sync",
            return_value=(25, True),
        ):
            coord._apply_shade("cover.test", cfg)

        await hass.async_block_till_done()
        assert len(fired) == 1
        assert fired[0].data["position"] == 25


# ════════════════════════════════════════════════════════════════════════════
# _apply_solar_gain
# ════════════════════════════════════════════════════════════════════════════

class TestApplySolarGain:

    def _enable_solar_gain(self, hass):
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["solar_gain"]["enable"] = True
        _set_switch(hass, "switch.test_auto_solar_gain", "on")

    def test_switch_off_skips(self, coord, hass):
        self._enable_solar_gain(hass)
        _set_switch(hass, "switch.test_auto_solar_gain", "off")
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]
        coord._apply_solar_gain("cover.test", cfg)
        assert coord._cover_queue.empty()

    def test_cover_unavailable_skips(self, coord, hass):
        self._enable_solar_gain(hass)
        hass.states.async_set("cover.test", "unavailable", {})
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]
        coord._apply_solar_gain("cover.test", cfg)
        assert coord._cover_queue.empty()

    def test_temperature_above_threshold_skips(self, coord, hass):
        self._enable_solar_gain(hass)
        hass.data[DOMAIN][DATA_SOLAR_GAIN] = {
            "temperature_entity": "sensor.temp",
            "temperature_threshold": 19.0,
        }
        hass.states.async_set("sensor.temp", "25.0")
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]
        coord._apply_solar_gain("cover.test", cfg)
        assert coord._cover_queue.empty()

    def test_temperature_entity_missing_skips(self, coord, hass):
        self._enable_solar_gain(hass)
        hass.data[DOMAIN][DATA_SOLAR_GAIN] = {"temperature_entity": "sensor.nonexistent"}
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]
        coord._apply_solar_gain("cover.test", cfg)
        assert coord._cover_queue.empty()

    def test_temperature_non_numeric_skips(self, coord, hass):
        self._enable_solar_gain(hass)
        hass.data[DOMAIN][DATA_SOLAR_GAIN] = {"temperature_entity": "sensor.temp"}
        hass.states.async_set("sensor.temp", "unavailable")
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]
        coord._apply_solar_gain("cover.test", cfg)
        assert coord._cover_queue.empty()

    def test_sun_facing_and_good_weather_uses_solar_position(self, coord, hass):
        self._enable_solar_gain(hass)
        hass.data[DOMAIN][DATA_SOLAR_GAIN] = {
            "weather_entity": "weather.home",
            "good_conditions": ["sunny"],
        }
        hass.states.async_set("weather.home", "sunny")
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]

        with patch(
            "custom_components.cover_extender.coordinator.compute_sun_facing",
            return_value=True,
        ):
            coord._apply_solar_gain("cover.test", cfg)

        assert not coord._cover_queue.empty()
        _, data = coord._cover_queue.get_nowait()
        assert data["position"] == 80  # position_solar

    def test_sun_not_facing_uses_cold_position(self, coord, hass):
        self._enable_solar_gain(hass)
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]

        with patch(
            "custom_components.cover_extender.coordinator.compute_sun_facing",
            return_value=False,
        ):
            coord._apply_solar_gain("cover.test", cfg)

        assert not coord._cover_queue.empty()
        _, data = coord._cover_queue.get_nowait()
        assert data["position"] == 10  # position_cold

    def test_bad_weather_uses_cold_position(self, coord, hass):
        self._enable_solar_gain(hass)
        hass.data[DOMAIN][DATA_SOLAR_GAIN] = {
            "weather_entity": "weather.home",
            "good_conditions": ["sunny"],
        }
        hass.states.async_set("weather.home", "cloudy")
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]

        with patch(
            "custom_components.cover_extender.coordinator.compute_sun_facing",
            return_value=True,
        ):
            coord._apply_solar_gain("cover.test", cfg)

        _, data = coord._cover_queue.get_nowait()
        assert data["position"] == 10  # position_cold because weather not ok

    def test_weather_entity_missing_defaults_to_cold(self, coord, hass):
        self._enable_solar_gain(hass)
        hass.data[DOMAIN][DATA_SOLAR_GAIN] = {
            "weather_entity": "weather.nonexistent",
            "good_conditions": ["sunny"],
        }
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]

        with patch(
            "custom_components.cover_extender.coordinator.compute_sun_facing",
            return_value=True,
        ):
            coord._apply_solar_gain("cover.test", cfg)

        _, data = coord._cover_queue.get_nowait()
        assert data["position"] == 10  # weather_ok=False

    def test_temperature_below_threshold_proceeds(self, coord, hass):
        self._enable_solar_gain(hass)
        hass.data[DOMAIN][DATA_SOLAR_GAIN] = {
            "temperature_entity": "sensor.temp",
            "temperature_threshold": 19.0,
        }
        hass.states.async_set("sensor.temp", "10.0")
        cfg = hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]

        with patch(
            "custom_components.cover_extender.coordinator.compute_sun_facing",
            return_value=False,
        ):
            coord._apply_solar_gain("cover.test", cfg)

        assert not coord._cover_queue.empty()


# ════════════════════════════════════════════════════════════════════════════
# _handle_select_mode_change
# ════════════════════════════════════════════════════════════════════════════

class TestHandleSelectModeChange:

    def _make_select_event(self, entity_id: str, old_state: str, new_state: str):
        event = MagicMock()
        event.data = {
            "entity_id": entity_id,
            "old_state": MagicMock(state=old_state),
            "new_state": MagicMock(state=new_state),
        }
        return event

    def test_same_state_is_ignored(self, coord, hass):
        coord._select_to_cover["select.mode_test"] = "cover.test"
        with patch.object(coord, "_apply_mode_core") as mock:
            coord._handle_select_mode_change(
                self._make_select_event("select.mode_test", "Day", "Day")
            )
            mock.assert_not_called()

    def test_unknown_select_is_ignored(self, coord, hass):
        with patch.object(coord, "_apply_mode_core") as mock:
            coord._handle_select_mode_change(
                self._make_select_event("select.mode_unknown", "Day", "Night")
            )
            mock.assert_not_called()

    def test_mode_change_creates_task(self, coord, hass):
        coord._select_to_cover["select.mode_test"] = "cover.test"
        with patch.object(hass, "async_create_task") as mock_task:
            coord._handle_select_mode_change(
                self._make_select_event("select.mode_test", "Day", "Night")
            )
            mock_task.assert_called_once()

    def test_missing_old_state_is_ignored(self, coord, hass):
        coord._select_to_cover["select.mode_test"] = "cover.test"
        event = MagicMock()
        event.data = {
            "entity_id": "select.mode_test",
            "old_state": None,
            "new_state": MagicMock(state="Night"),
        }
        with patch.object(coord, "_apply_mode_core") as mock:
            coord._handle_select_mode_change(event)
            mock.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# _handle_mode_entity_change
# ════════════════════════════════════════════════════════════════════════════

class TestHandleModeEntityChange:

    def test_active_mode_enqueues_position(self, coord, hass):
        # Wire entity_mode_map: sensor.pos → [("cover.test", "Day")]
        coord._entity_mode_map["sensor.pos"] = [("cover.test", "Day")]
        # Cover's current mode is "Day"
        hass.states.async_set("select.mode_test", "Day")
        hass.states.async_set("sensor.pos", "60")
        _set_switch(hass, "switch.test_lock", "off")

        event = MagicMock()
        event.data = {
            "entity_id": "sensor.pos",
            "new_state": MagicMock(state="60"),
        }
        with patch.object(hass, "async_create_task") as mock_task:
            coord._handle_mode_entity_change(event)
            mock_task.assert_called_once()

    def test_inactive_mode_does_not_enqueue(self, coord, hass):
        coord._entity_mode_map["sensor.pos"] = [("cover.test", "Night")]
        hass.states.async_set("select.mode_test", "Day")  # current mode != Night

        event = MagicMock()
        event.data = {
            "entity_id": "sensor.pos",
            "new_state": MagicMock(state="40"),
        }
        with patch.object(hass, "async_create_task") as mock_task:
            coord._handle_mode_entity_change(event)
            mock_task.assert_not_called()

    def test_non_numeric_new_state_ignored(self, coord, hass):
        coord._entity_mode_map["sensor.pos"] = [("cover.test", "Day")]
        hass.states.async_set("select.mode_test", "Day")

        event = MagicMock()
        event.data = {
            "entity_id": "sensor.pos",
            "new_state": MagicMock(state="unavailable"),
        }
        with patch.object(hass, "async_create_task") as mock_task:
            coord._handle_mode_entity_change(event)
            mock_task.assert_not_called()

    def test_missing_new_state_ignored(self, coord, hass):
        event = MagicMock()
        event.data = {"entity_id": "sensor.pos", "new_state": None}
        with patch.object(hass, "async_create_task") as mock_task:
            coord._handle_mode_entity_change(event)
            mock_task.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# _handle_solar_gain_trigger
# ════════════════════════════════════════════════════════════════════════════

class TestHandleSolarGainTrigger:

    def test_trigger_calls_apply_for_enabled_covers(self, coord, hass):
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["solar_gain"]["enable"] = True
        with patch.object(coord, "_apply_solar_gain") as mock:
            coord._handle_solar_gain_trigger()
            mock.assert_called_once_with(
                "cover.test",
                hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"],
            )

    def test_trigger_skips_disabled_covers(self, coord, hass):
        # solar_gain.enable is False by default
        with patch.object(coord, "_apply_solar_gain") as mock:
            coord._handle_solar_gain_trigger()
            mock.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# _handle_cover_state_change
# ════════════════════════════════════════════════════════════════════════════

class TestHandleCoverStateChange:

    def test_unavailable_cover_skipped(self, coord, hass):
        event = MagicMock()
        event.data = {
            "entity_id": "cover.test",
            "new_state": MagicMock(state="unavailable", attributes={}),
        }
        # Should not raise or inject attrs
        coord._handle_cover_state_change(event)

    def test_unknown_cover_skipped(self, coord, hass):
        event = MagicMock()
        event.data = {
            "entity_id": "cover.unknown",
            "new_state": MagicMock(state="open", attributes={"current_position": 50}),
        }
        coord._handle_cover_state_change(event)

    def test_missing_new_state_skipped(self, coord, hass):
        event = MagicMock()
        event.data = {"entity_id": "cover.test", "new_state": None}
        coord._handle_cover_state_change(event)  # should not raise

    def test_attrs_injected_on_state_change(self, coord, hass):
        hass.states.async_set("cover.test", "open", {"current_position": 50})
        state = hass.states.get("cover.test")

        event = MagicMock()
        event.data = {"entity_id": "cover.test", "new_state": state}
        coord._handle_cover_state_change(event)

        new_state = hass.states.get("cover.test")
        # build_extra_attrs injects "auto_shade" at minimum
        assert "auto_shade" in new_state.attributes


# ════════════════════════════════════════════════════════════════════════════
# Service handlers
# ════════════════════════════════════════════════════════════════════════════

class TestServiceGetModePosition:

    async def test_known_cover_and_mode_returns_position(self, coord, hass):
        call = MagicMock()
        call.data = {"entity_id": "cover.test", "mode": "Day"}
        result = await coord.service_get_mode_position(call)
        assert result == {"position": 40}

    async def test_unknown_cover_returns_none(self, coord, hass):
        call = MagicMock()
        call.data = {"entity_id": "cover.other", "mode": "Day"}
        result = await coord.service_get_mode_position(call)
        assert result == {"position": None}

    async def test_unknown_mode_returns_none(self, coord, hass):
        call = MagicMock()
        call.data = {"entity_id": "cover.test", "mode": "Unknown"}
        result = await coord.service_get_mode_position(call)
        assert result == {"position": None}


class TestServiceComputeShadePosition:

    async def test_returns_position_and_flag(self, coord, hass):
        call = MagicMock()
        call.data = {"entity_id": "cover.test"}
        with patch(
            "custom_components.cover_extender.coordinator.compute_shade_sync",
            return_value=(42, True),
        ):
            result = await coord.service_compute_shade_position(call)
        assert result["position"] == 42
        assert result["should_update"] is True


class TestServiceOpenCloseCover:

    async def test_open_cover_enqueues_100(self, coord, hass):
        _set_switch(hass, "switch.test_lock", "off")
        call = MagicMock()
        call.data = {"entity_id": ["cover.test"]}
        await coord.service_open_cover(call)
        _, data = coord._cover_queue.get_nowait()
        assert data["position"] == 100

    async def test_close_cover_enqueues_0(self, coord, hass):
        _set_switch(hass, "switch.test_lock", "off")
        call = MagicMock()
        call.data = {"entity_id": ["cover.test"]}
        await coord.service_close_cover(call)
        _, data = coord._cover_queue.get_nowait()
        assert data["position"] == 0

    async def test_open_cover_with_lock_stores_memory(self, coord, hass):
        _set_switch(hass, "switch.test_lock", "on")
        call = MagicMock()
        call.data = {"entity_id": ["cover.test"]}
        await coord.service_open_cover(call)
        assert hass.data[DOMAIN][DATA_MEMORY]["cover.test"] == 100


class TestServiceApplyMemory:

    async def test_with_memory_enqueues(self, coord, hass):
        hass.data[DOMAIN][DATA_MEMORY]["cover.test"] = 55
        call = MagicMock()
        call.data = {"entity_id": ["cover.test"]}
        await coord.service_apply_memory(call)
        service, data = coord._cover_queue.get_nowait()
        assert service == "set_cover_position"
        assert data["position"] == 55

    async def test_without_memory_does_nothing(self, coord, hass):
        call = MagicMock()
        call.data = {"entity_id": ["cover.test"]}
        await coord.service_apply_memory(call)
        assert coord._cover_queue.empty()


class TestServiceApplyMode:

    async def test_mode_not_in_profile_is_skipped(self, coord, hass):
        hass.services.async_register("select", "select_option", AsyncMock())
        call = MagicMock()
        call.data = {"mode": "Nonexistent", "entity_id": ["cover.test"]}
        result = await coord.service_apply_mode(call)
        assert "cover.test" in result["skipped"]
        assert result["applied"] == []

    async def test_select_entity_missing_is_skipped(self, coord, hass):
        # No select.mode_test in state machine
        call = MagicMock()
        call.data = {"mode": "Day", "entity_id": ["cover.test"]}
        result = await coord.service_apply_mode(call)
        assert "cover.test" in result["skipped"]

    async def test_valid_mode_applied(self, coord, hass):
        hass.states.async_set("select.mode_test", "Night")
        select_calls = []

        async def record(call):
            select_calls.append(dict(call.data))

        hass.services.async_register("select", "select_option", record)
        call = MagicMock()
        call.data = {"mode": "Day", "entity_id": ["cover.test"]}
        result = await coord.service_apply_mode(call)
        assert "cover.test" in result["applied"]
        assert any(c["option"] == "Day" for c in select_calls)


# ════════════════════════════════════════════════════════════════════════════
# async_stop
# ════════════════════════════════════════════════════════════════════════════

class TestAsyncStop:

    async def test_stop_cancels_worker(self, coord, hass):
        coord._start_worker()
        assert coord._worker_task is not None
        assert not coord._worker_task.done()
        await coord.async_stop()
        await hass.async_block_till_done()
        assert coord._worker_task.done()

    async def test_stop_clears_unsubs(self, coord, hass):
        unsub_called = []
        coord._unsubs = [lambda: unsub_called.append(True)]
        await coord.async_stop()
        assert len(unsub_called) == 1
        assert coord._unsubs == []

    async def test_stop_with_no_worker_is_safe(self, coord, hass):
        coord._worker_task = None
        await coord.async_stop()  # must not raise


# ════════════════════════════════════════════════════════════════════════════
# _inject_sun_facing
# ════════════════════════════════════════════════════════════════════════════

class TestInjectSunFacing:

    def test_sun_facing_injected_into_cover_attrs(self, coord, hass):
        hass.states.async_set("cover.test", "open", {"current_position": 50})
        with patch(
            "custom_components.cover_extender.coordinator.compute_sun_facing",
            return_value=True,
        ):
            coord._inject_sun_facing()

        state = hass.states.get("cover.test")
        assert state.attributes.get("sun_facing") is True

    def test_unavailable_cover_skipped(self, coord, hass):
        hass.states.async_set("cover.test", "unavailable", {})
        with patch(
            "custom_components.cover_extender.coordinator.compute_sun_facing",
        ) as mock:
            coord._inject_sun_facing()
            mock.assert_not_called()

    def test_shade_applied_when_enabled(self, coord, hass):
        hass.states.async_set("cover.test", "open", {"current_position": 50})
        with patch(
            "custom_components.cover_extender.coordinator.compute_sun_facing",
            return_value=None,
        ):
            with patch.object(coord, "_apply_shade") as mock_shade:
                coord._inject_sun_facing()
                mock_shade.assert_called_once()

    def test_solar_gain_not_applied_when_disabled(self, coord, hass):
        hass.states.async_set("cover.test", "open", {"current_position": 50})
        with patch(
            "custom_components.cover_extender.coordinator.compute_sun_facing",
            return_value=None,
        ):
            with patch.object(coord, "_apply_solar_gain") as mock_sg:
                coord._inject_sun_facing()
                mock_sg.assert_not_called()
